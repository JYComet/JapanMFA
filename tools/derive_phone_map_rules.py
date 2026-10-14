#!/usr/bin/env python3
"""Derive candidate Japanese MFA v3 phone-map rules from production evidence.

The bundled ``japanese_mfa_v3_phone_map.yaml`` bridges a locked Katakana reading
(mora by mora) to the flat phone sequence produced by the MFA Japanese G2P.  When
a reading cannot be bridged the whole utterance fails preparation with
``no_mappable_pronunciation``.  This tool measures exactly which readings the
current map cannot bridge (over the real G2P cache), proposes the minimal set of
extra rules needed, cross-checks them against the official MFA dictionary, and
writes a candidate map plus an auditable report.  It never modifies the bundled
map or any production file.

Evidence sources
----------------
* primary: the production G2P cache
  (``.../native-word-cache/native-words.sqlite3``, ``stage='g2p'``) - the exact
  ``reading -> phones`` pairs the pipeline feeds to the matcher.
* cross-check: the official ``japanese_mfa-v3.0.0.dict`` (``kana -> phones``).

The derivation is a constrained monotone DP over ``(mora_index, phone_index)``:
existing rules cost nothing (maximising reuse); novel contiguous chunks are only
allowed in linguistically valid shapes and are price-discounted when they agree
with a mora's already-observed phone profile, so a CV mora is not split into its
consonant and vowel.  Only novel chunks with ``support >= min-support`` survive.

Every G2P candidate (primary phones *and* alternates) is aligned, because
``filter_mappable_pronunciations`` accepts a reading if any candidate maps - a
reading an alternate already covers needs no new rule.  A chunk that could only
arise from the G2P dropping a phone (a ``ッ`` with no geminate/glottal phone, a
``ー`` with no length-marked phone, or a mora yielding fewer phones than its
profile minimum) is priced as impossible, so such readings stay rejected instead
of being bridged by a bogus rule.
"""

from __future__ import annotations

import argparse
import collections
import json
import sqlite3
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

from japanmfa.domain import Token  # noqa: E402
from japanmfa.frontend.mora import segment_morae  # noqa: E402
from japanmfa.mfa.phone_map import PhoneMap  # noqa: E402

DEFAULT_MAP = REPO / "src/japanmfa/mfa/data/japanese_mfa_v3_phone_map.yaml"

# Phone shapes a single novel chunk may take.  Every allowed shape has implicit
# mora spans (one side is a singleton or both sides are equal length) so a
# generated rule never needs hand-authored ``mora_spans``.
CHUNK_SHAPES = ((1, 1), (1, 2), (1, 3), (2, 1), (2, 2), (3, 1), (3, 3))

# Base costs.  Lower wins; existing-rule matches are always cost 0.
COST_BASE = 20.0
COST_PER_EXTRA_MORA = 12.0
COST_PER_EXTRA_PHONE = 6.0
DISCOUNT_PROFILE_MATCH = 8.0   # chunk phones match this mora's observed count
PENALTY_PROFILE_MISMATCH = 14.0  # single mora whose phone count is unattested
DISCOUNT_MERGE = 10.0          # ッ / ー driven merge across morae
PENALTY_MERGE_WITHOUT_MARK = 10.0  # multi-mora chunk with no ッ/ー bridge

# A chunk this expensive is linguistically impossible, not merely disfavoured.
# It makes a coverage "unsolvable" rather than forcing a bogus rule.
IMPLAUSIBLE_PENALTY = 10000.0

STANDALONE = {"ッ", "ン"}
MARKERS = {"ッ", "ー"}
SMALL_KANA = frozenset("ァィゥェォャュョヮヵヶ")
VOWEL_BASES = {"a", "i", "ɯ", "e", "o", "ɨ"}
VOWELS = VOWEL_BASES | {base + "ː" for base in VOWEL_BASES}


def _expected_counts(phone_map: PhoneMap,
                     proposals: dict | None = None,
                     min_evidence: int = 5) -> dict[str, int]:
    """Expected phone count for each mora - how many phones it should own.

    Curated 1-mora rules win where they exist; otherwise the most frequent
    1-mora chunk from a previous derivation pass is used.  This is the prior
    that stops a CV mora being split into its consonant and vowel: with the
    count known, the correct 1-mora->2-phone chunk is discounted and the
    consonant-only or vowel-only split is penalised.
    """
    expected: dict[str, int] = {}
    inconsistent: dict[str, set[int]] = {}
    for rule in phone_map.rules:
        if len(rule.kana) == 1:
            counts = inconsistent.setdefault(rule.kana[0], set())
            counts.add(len(rule.phones))
    for mora, counts in inconsistent.items():
        if len(counts) == 1:
            expected[mora] = counts.pop()
    # most frequent derived 1-mora chunk fills the morae the map has never seen
    if proposals:
        best: dict[str, tuple[int, int]] = {}
        for (kana, phones), sources in proposals.items():
            if len(kana) != 1:
                continue
            support = len(sources)
            if support < min_evidence:
                continue
            current = best.get(kana[0])
            if current is None or support > current[0]:
                best[kana[0]] = (support, len(phones))
        for mora, (_support, count) in best.items():
            expected.setdefault(mora, count)
    return expected


def _index_rules(
    rules: list[tuple[tuple[str, ...], tuple[str, ...]]],
) -> dict[str, list[tuple[tuple[str, ...], tuple[str, ...]]]]:
    """Group rules by their leading mora so the DP only scans reachable rules."""
    index: dict[str, list[tuple[tuple[str, ...], tuple[str, ...]]]] = collections.defaultdict(list)
    for kana, phones in rules:
        index[kana[0]].append((kana, phones))
    return index


def align(
    morae: tuple[str, ...],
    phones: tuple[str, ...],
    rules_by_first: dict[str, list[tuple[tuple[str, ...], tuple[str, ...]]]],
    expected: dict[str, int],
) -> tuple[float, list[tuple[tuple[str, ...], tuple[str, ...]]]] | None:
    """Return (cost, novel_chunks) for the cheapest coverage, or None."""
    n, m = len(morae), len(phones)
    best: dict[tuple[int, int], tuple[float, list]] = {(0, 0): (0.0, [])}

    def relax(key: tuple[int, int], value: tuple[float, list]) -> None:
        current = best.get(key)
        if current is None or value[0] < current[0]:
            best[key] = value

    for i in range(n + 1):
        for j in range(m + 1):
            state = best.get((i, j))
            if state is None or i >= n or j >= m:
                continue
            cost, chunks = state
            # 1) reuse an existing rule (free)
            for kana, rule_phones in rules_by_first.get(morae[i], ()):
                ki, pj = len(kana), len(rule_phones)
                if i + ki <= n and j + pj <= m and morae[i:i + ki] == kana and phones[j:j + pj] == rule_phones:
                    relax((i + ki, j + pj), (cost, chunks))
            # 2) constrained novel chunk
            for ki, pj in CHUNK_SHAPES:
                if i + ki > n or j + pj > m:
                    continue
                chunk_kana = morae[i:i + ki]
                chunk_phones = phones[j:j + pj]
                novel_cost = _novel_cost(chunk_kana, chunk_phones, expected)
                relax((i + ki, j + pj),
                      (cost + novel_cost, chunks + [(chunk_kana, chunk_phones)]))
    return best.get((n, m))


def _implausible(kana: tuple[str, ...], phones: tuple[str, ...],
                 expected: dict[str, int]) -> bool:
    """True when a chunk could only arise from the G2P dropping phones.

    Guards, all grounded in how the japanese_mfa G2P degrades:

    * ``ー`` is a length marker, not a mora that owns phones; it must merge
      into a vowel-bearing neighbour.
    * a 促音 ``ッ`` must surface as a geminate (``ː``) or glottal (``Q``/``ʔ``);
      a long-vowel ``ー`` must surface as a length-marked phone.  When neither
      appears the marker's phone was dropped rather than realised.
    * every ordinary mora contributes the phones it is expected to own; a
      chunk with fewer phones than that sum lost a consonant or vowel.
      ``ッ`` / ``ー`` are exempt because they merge into a neighbour by design.
    """
    if kana == ("ー",):
        return True
    if "ッ" in kana:
        if kana == ("ッ",):
            # a lone 促音 realises exactly its own geminate/glottal phone
            if len(phones) != 1:
                return True
        elif not _has_consonant_geminate(phones):
            # ッ+X: the 促音 must lengthen X's own consonant, not a vowel
            return True
    if "ー" in kana and not any(phone.endswith("ː") for phone in phones):
        return True
    if kana[0] in STANDALONE and phones and phones[0] in VOWELS:
        # ン is a nasal coda: a leading vowel means its phone was dropped and a
        # neighbour's vowel was pushed onto it
        return True
    if kana[0] not in MARKERS and expected.get(kana[0], 0) >= 2:
        # a CV mora owning several phones must start its chunk with its consonant
        if phones and phones[0] in VOWELS:
            return True
    needed = sum(_min_phones(mora, expected, len(kana) == 1) for mora in kana)
    return len(phones) < needed


def _min_phones(mora: str, expected: dict[str, int], single_mora: bool) -> int:
    """Fewest phones a mora must contribute to a chunk.

    A lone 拗音 / 外来音 digraph (base kana + small kana, e.g. リョ in ミリョウ)
    may keep only its consonant, because its vowel merges into a following
    拗長音 (リョウ = ɾʲoː).  Inside a multi-mora chunk that exemption is withheld:
    otherwise it would let a neighbouring mora (e.g. the ン in ン+ヒャ) collapse
    to nothing.  Every other mora must contribute its full expected count.
    """
    if mora in MARKERS:
        return 0
    want = expected.get(mora, 0)
    if single_mora and len(mora) >= 2 and mora[-1] in SMALL_KANA:
        return 1 if want else 0
    return want


def _has_consonant_geminate(phones: tuple[str, ...]) -> bool:
    return any(
        phone in {"Q", "ʔ"} or (phone.endswith("ː") and phone[0] not in VOWEL_BASES)
        for phone in phones
    )


def _novel_cost(kana: tuple[str, ...], phones: tuple[str, ...],
                expected: dict[str, int]) -> float:
    if _implausible(kana, phones, expected):
        return IMPLAUSIBLE_PENALTY
    cost = COST_BASE + COST_PER_EXTRA_MORA * (len(kana) - 1) + COST_PER_EXTRA_PHONE * (len(phones) - 1)
    if len(kana) == 1:
        want = expected.get(kana[0])
        if want is not None:
            if len(phones) == want:
                cost -= DISCOUNT_PROFILE_MATCH
            else:
                cost += PENALTY_PROFILE_MISMATCH
    else:
        # Only ッ / ー justify a merge across morae: they own no phone of their
        # own.  ン owns a phone, so ン+X must not undercut the existing ン rule.
        if any(mora in MARKERS for mora in kana):
            cost -= DISCOUNT_MERGE
        else:
            cost += PENALTY_MERGE_WITHOUT_MARK
    return cost


def _load_g2p_cache(path: Path) -> list[tuple[str, tuple[tuple[str, ...], ...]]]:
    """Read every G2P result: the primary phones plus its alternates.

    ``filter_mappable_pronunciations`` accepts a reading when *any* candidate
    maps, so the derivation must consider all of them too - otherwise it invents
    making-up rules for readings an alternate already covers.
    """
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    rows = connection.execute("SELECT request, payload FROM words WHERE stage='g2p'").fetchall()
    connection.close()
    readings = []
    for request, payload in rows:
        reading = json.loads(request)
        data = json.loads(payload)
        candidates = (tuple(data["phones"]), *(tuple(item) for item in data.get("alternates", ())))
        readings.append((reading, candidates))
    return readings


def _load_official_dict(path: Path) -> list[str]:
    """Yield (kana, phones) pairs from the official MFA dictionary."""
    entries = []
    if not path.is_file():
        return entries
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            kana, rest = parts[0], parts[1:]
            phones = [token for token in rest if not _is_number(token)]
            if phones:
                entries.append((kana, tuple(phones)))
    return entries


def _is_number(token: str) -> bool:
    try:
        float(token)
        return True
    except ValueError:
        return False


def _dict_confirmation(entries: list[tuple[str, tuple[str, ...]]],
                       candidates: list[tuple[tuple[str, ...], tuple[str, ...]]]) -> dict[tuple[str, ...], bool]:
    """For each candidate chunk, is its (kana, phones) pattern in the dict?

    A candidate is confirmed when some official entry's kana contains the chunk
    kana and the chunk phones appear as a contiguous sub-span of that entry's
    phones.  This is corroboration, not proof - a substring occurrence is a
    weaker guarantee than a whole-word match, but it filters out patterns the
    official dictionary never produces.
    """
    wanted = {kana: tuple(phones) for kana, phones in candidates}
    kana_texts = sorted(wanted, key=lambda kana: -len("".join(kana)))
    confirmed: dict[tuple[str, ...], bool] = {kana: False for kana in wanted}
    remaining = len(kana_texts)
    for entry_kana, entry_phones in entries:
        if remaining == 0:
            break
        for kana in kana_texts:
            if confirmed[kana]:
                continue
            text = "".join(kana)
            if len(text) > len(entry_kana) or text not in entry_kana:
                continue
            want = wanted[kana]
            span = len(want)
            for start in range(len(entry_phones) - span + 1):
                if tuple(entry_phones[start:start + span]) == want:
                    confirmed[kana] = True
                    remaining -= 1
                    break
    return confirmed


def _derive_pass(
    readings: list[tuple[str, tuple[tuple[str, ...], ...]]],
    phone_map: PhoneMap,
    rules_by_first: dict,
    existing: set,
    expected: dict[str, int],
) -> dict:
    """Align every reading and collect the novel chunks an expansion would need."""
    proposals: dict[tuple[tuple[str, ...], tuple[str, ...]], list[str]] = collections.defaultdict(list)
    memo: dict[tuple[tuple[str, ...], tuple[str, ...]], tuple[float, list] | None] = {}
    morae_memo: dict[str, tuple[str, ...] | None] = {}
    stats = {"readings_total": len(readings), "readings_already_ok": 0,
             "readings_need_novel": 0, "readings_unsolved": 0}
    for reading, candidates in readings:
        if reading in morae_memo:
            morae = morae_memo[reading]
        else:
            try:
                morae = tuple(mora.kana for mora in segment_morae(Token(0, 0, len(reading), reading, (), reading, "sudachi")))
            except Exception:
                morae = None
            morae_memo[reading] = morae
        if morae is None:
            continue
        # Best coverage across every G2P candidate, exactly as production tries them.
        best: tuple[float, list] | None = None
        for candidate in candidates:
            normalized = tuple(phone_map.normalize(phone) for phone in candidate)
            key = (morae, normalized)
            if key in memo:
                result = memo[key]
            else:
                result = align(morae, normalized, rules_by_first, expected)
                memo[key] = result
            if result is None:
                continue
            if best is None or result[0] < best[0]:
                best = result
            if best[0] == 0.0:
                break
        if best is None:
            stats["readings_unsolved"] += 1
            continue
        cost, chunks = best
        if cost == 0.0:
            stats["readings_already_ok"] += 1
            continue
        if cost >= IMPLAUSIBLE_PENALTY:
            # every candidate needs a phone the G2P dropped - stays rejected
            stats["readings_unsolved"] += 1
            continue
        stats["readings_need_novel"] += 1
        for chunk in chunks:
            if chunk in existing:
                continue
            proposals[chunk].append(reading)
    return {"proposals": proposals, "stats": stats}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--g2p-cache", type=Path, required=True)
    parser.add_argument("--official-dict", type=Path, default=None)
    parser.add_argument("--min-support", type=int, default=10)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    phone_map = PhoneMap.load(args.map)
    existing = {(rule.kana, rule.phones) for rule in phone_map.rules}
    rules_by_first = _index_rules([(rule.kana, rule.phones) for rule in phone_map.rules])

    readings = _load_g2p_cache(args.g2p_cache)

    # Pass 1 discovers mora phone-count profiles; pass 2 re-derives with them,
    # because a mora the map has never seen has no count to prefer the correct
    # 1-mora->2-phone chunk over a consonant/vowel split.
    expected = _expected_counts(phone_map)
    first = _derive_pass(readings, phone_map, rules_by_first, existing, expected)
    expected = _expected_counts(phone_map, first["proposals"])
    second = _derive_pass(readings, phone_map, rules_by_first, existing, expected)
    stats, proposals = second["stats"], second["proposals"]

    strong = [(kana, phones) for (kana, phones), sources in proposals.items() if len(sources) >= args.min_support]
    official = _load_official_dict(args.official_dict) if args.official_dict else []
    confirmed = _dict_confirmation(official, strong) if official else {}
    rules_out = []
    for kana, phones in strong:
        sources = proposals[(kana, phones)]
        entry = {"kana": list(kana), "phones": list(phones),
                 "support": len(sources), "observed_sources": sorted(set(sources))[:20]}
        if official:
            entry["official_dict_confirmed"] = confirmed.get(kana, False)
        rules_out.append(entry)
    rules_out.sort(key=lambda item: (-item["support"], item["kana"], item["phones"]))

    confirmed_count = sum(1 for entry in rules_out if entry.get("official_dict_confirmed"))
    report = {
        "generated_at": time.time(),
        "map": str(args.map),
        "map_rule_count_before": len(phone_map.rules),
        "g2p_cache": str(args.g2p_cache),
        "official_dict": str(args.official_dict) if args.official_dict else None,
        **stats,
        "distinct_chunks_observed": len(proposals),
        "min_support": args.min_support,
        "expected_mora_phone_counts": expected,
        "candidate_rule_count": len(rules_out),
        "candidate_official_dict_confirmed": confirmed_count,
        "candidate_official_dict_unconfirmed": len(rules_out) - confirmed_count,
        "candidate_rules": rules_out,
    }

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.out / "proposed-rules.json").write_text(
        json.dumps({"rules": [{"kana": item["kana"], "phones": item["phones"],
                               "support": item["support"], "observed_sources": item["observed_sources"]}
                              for item in rules_out]}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    original = args.map.read_text(encoding="utf-8")
    (args.out / "phone-map.before.yaml").write_text(original, encoding="utf-8")
    appended = _render_candidate(original, rules_out)
    (args.out / "candidate-map.yaml").write_text(appended, encoding="utf-8")

    print(json.dumps({key: report[key] for key in (
        "readings_total", "readings_already_ok", "readings_need_novel",
        "readings_unsolved", "distinct_chunks_observed", "candidate_rule_count")}, ensure_ascii=False))
    return 0


def _render_candidate(original: str, rules_out: list[dict]) -> str:
    """Append the candidate rules to the original YAML text, keeping comments."""
    lines = [original.rstrip("\n"), "", "# --- derived candidate rules (generated) ---"]
    for item in rules_out:
        lines.append("  - kana: [" + ", ".join(item["kana"]) + "]")
        lines.append("    phones: [" + ", ".join(item["phones"]) + "]")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
