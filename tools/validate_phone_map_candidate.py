#!/usr/bin/env python3
"""Validate a candidate phone map against the production G2P cache.

Compares the bundled (current) map with a candidate map over every
``reading -> candidate phones`` pair the pipeline actually feeds to the matcher
and reports:

* **regression** - readings that map today whose grouping changes (or is lost)
  under the candidate.  Must be zero.
* **positives** - readings that fail today and map under the candidate.
* **negatives** - readings that fail today and must keep failing (e.g. the G2P
  dropped a phone); reported with their reason codes.
* **new ambiguity** - readings that newly raise
  ``ambiguous_mora_phone_mapping`` (never acceptable).

The matcher is re-implemented here with rules bucketed by their leading mora so
the full cache is feasible; :func:`check_equivalence` proves the fast path
agrees with ``projection._match_morae_to_phones`` on a random sample before the
full sweep runs.  Nothing is written except the report.
"""

from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

from japanmfa.domain import Mora, Token  # noqa: E402
from japanmfa.frontend.mora import segment_morae  # noqa: E402
from japanmfa.mfa.phone_map import PhoneMap  # noqa: E402
from japanmfa.projection import _match_morae_to_phones  # noqa: E402

DEFAULT_MAP = REPO / "src/japanmfa/mfa/data/japanese_mfa_v3_phone_map.yaml"
DERIVE_TOOL = Path(__file__).resolve().parent / "derive_phone_map_rules.py"


def _load_derive_module():
    spec = importlib.util.spec_from_file_location("derive_phone_map_rules", DERIVE_TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _index_rules(phone_map: PhoneMap) -> dict[str, tuple]:
    index: dict[str, list] = collections.defaultdict(list)
    for rule in phone_map.rules:
        index[rule.kana[0]].append(rule)
    return index


def match_fast(morae_kana: tuple[str, ...], phones: tuple[str, ...],
               phone_map: PhoneMap, rules_by_first: dict[str, tuple]) -> tuple:
    """Fast replica of the production matcher; returns ("ok", mapping) or ("fail", reason)."""
    normalized = tuple(phone_map.normalize(phone) for phone in phones)
    n, m = len(morae_kana), len(normalized)
    states: dict[tuple[int, int], tuple[int, int, tuple]] = {(0, 0): (0, 1, ())}
    for mora_index in range(n + 1):
        for phone_index in range(m + 1):
            state = states.get((mora_index, phone_index))
            if state is None or mora_index >= n or phone_index >= m:
                continue
            cost, count, mapping = state
            for rule in rules_by_first.get(morae_kana[mora_index], ()):
                mora_end = mora_index + len(rule.kana)
                phone_end = phone_index + len(rule.phones)
                if mora_end > n or phone_end > m:
                    continue
                if morae_kana[mora_index:mora_end] != rule.kana:
                    continue
                if normalized[phone_index:phone_end] != rule.phones:
                    continue
                new_mapping = mapping + tuple(
                    morae_kana[mora_index + start: mora_index + end]
                    for start, end in rule.mora_spans
                )
                candidate = (cost + rule.cost, count, new_mapping)
                current = states.get((mora_end, phone_end))
                if current is None or candidate[0] < current[0]:
                    states[(mora_end, phone_end)] = candidate
                elif candidate[0] == current[0]:
                    states[(mora_end, phone_end)] = (
                        current[0], min(2, current[1] + candidate[1]), current[2]
                    )
    result = states.get((n, m))
    if result is None:
        if any(phone not in phone_map.known_phones for phone in normalized):
            return ("fail", "unknown_phone")
        return ("fail", "mora_phone_mapping")
    if result[1] != 1:
        return ("fail", "ambiguous_mora_phone_mapping")
    return ("ok", result[2])


def check_equivalence(samples: list[tuple[tuple[str, ...], tuple[str, ...]]],
                      phone_map: PhoneMap, rules_by_first: dict, rng: random.Random) -> dict:
    """Assert match_fast agrees with the production matcher on the given samples."""
    mismatches = []
    for morae_kana, phones in samples:
        morae = tuple(Mora(0, index, kana, "H") for index, kana in enumerate(morae_kana))
        try:
            mapping = _match_morae_to_phones(morae, phones, phone_map)
            expected = ("ok", tuple(tuple(mora.kana for mora in group) for group in mapping))
        except Exception as exc:  # StageFailure carries the reason code
            expected = ("fail", getattr(exc, "reason_code", "unknown"))
        actual = match_fast(morae_kana, phones, phone_map, rules_by_first)
        if expected != actual:
            mismatches.append({"morae": list(morae_kana), "phones": list(phones),
                               "production": [expected[0], _stringify(expected[1])],
                               "fast": [actual[0], _stringify(actual[1])]})
    return {"checked": len(samples), "mismatches": mismatches[:20], "mismatch_count": len(mismatches)}


def _stringify(value: object) -> object:
    if isinstance(value, tuple):
        return [_stringify(item) for item in value]
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--g2p-cache", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=None,
                        help="cap the number of distinct readings (for a quick smoke run)")
    parser.add_argument("--equivalence-samples", type=int, default=3000)
    parser.add_argument("--seed", type=int, default=20261008)
    args = parser.parse_args()

    derive = _load_derive_module()
    current = PhoneMap.load(args.map)
    candidate = PhoneMap.load(args.candidate)
    current_idx = _index_rules(current)
    candidate_idx = _index_rules(candidate)

    readings = derive._load_g2p_cache(args.g2p_cache)
    morae_cache: dict[str, tuple[str, ...] | None] = {}
    keys: dict[tuple[tuple[str, ...], tuple[str, ...]], None] = {}
    for reading, candidates in readings:
        if reading not in morae_cache:
            try:
                morae_cache[reading] = tuple(
                    mora.kana for mora in segment_morae(
                        Token(0, 0, len(reading), reading, (), reading, "sudachi"))
                )
            except Exception:
                morae_cache[reading] = None
        morae = morae_cache[reading]
        if morae is None:
            continue
        for phones in candidates:
            keys[(morae, tuple(phones))] = None
    unique = list(keys)
    unique.sort()
    if args.limit:
        unique = unique[:args.limit]

    rng = random.Random(args.seed)
    sample = rng.sample(unique, min(args.equivalence_samples, len(unique)))
    equivalence = check_equivalence(sample, current, current_idx, rng)
    equivalence_candidate = check_equivalence(sample, candidate, candidate_idx, rng)

    regressions: list[dict] = []
    positives: list[dict] = []
    negatives: list[dict] = []
    new_ambiguity: list[dict] = []
    current_ok = candidate_ok = 0
    transitions: collections.Counter = collections.Counter()
    negative_reasons: collections.Counter = collections.Counter()

    for morae, phones in unique:
        oc = match_fast(morae, phones, current, current_idx)
        nc = match_fast(morae, phones, candidate, candidate_idx)
        if oc[0] == "ok":
            current_ok += 1
        if nc[0] == "ok":
            candidate_ok += 1
        if oc[0] == "ok" and nc[0] == "ok":
            if oc[1] != nc[1]:
                regressions.append({"morae": list(morae), "phones": list(phones),
                                    "before": _stringify(oc[1]), "after": _stringify(nc[1])})
        elif oc[0] == "ok" and nc[0] == "fail":
            regressions.append({"morae": list(morae), "phones": list(phones),
                                "before": _stringify(oc[1]), "after_reason": nc[1]})
        elif oc[0] == "fail" and nc[0] == "ok":
            positives.append({"morae": list(morae), "phones": list(phones),
                              "was": oc[1], "mapping": _stringify(nc[1])})
            transitions[oc[1]] += 1
        else:
            negatives.append({"morae": list(morae), "phones": list(phones), "reason": nc[1],
                              "was": oc[1]})
            negative_reasons[nc[1]] += 1
        if nc[0] == "fail" and nc[1] == "ambiguous_mora_phone_mapping" and oc != ("fail", "ambiguous_mora_phone_mapping"):
            new_ambiguity.append({"morae": list(morae), "phones": list(phones), "was": oc[1]})

    report = {
        "candidate": str(args.candidate),
        "map": str(args.map),
        "map_rule_count_before": len(current.rules),
        "map_rule_count_after": len(candidate.rules),
        "distinct_keys": len(unique),
        "keys_limited_to": args.limit,
        "current_mappable": current_ok,
        "candidate_mappable": candidate_ok,
        "positives": len(positives),
        "negatives": len(negatives),
        "regressions": len(regressions),
        "new_ambiguity": len(new_ambiguity),
        "positive_transitions": dict(transitions),
        "negative_reasons": dict(negative_reasons),
        "equivalence_current": equivalence,
        "equivalence_candidate": equivalence_candidate,
        "positive_samples": positives[:40],
        "negative_samples": negatives[:40],
        "regression_samples": regressions[:40],
        "new_ambiguity_samples": new_ambiguity[:40],
        "verdict": {
            "no_regression": not regressions,
            "no_new_ambiguity": not new_ambiguity,
            "matcher_verified": not equivalence["mismatch_count"] and not equivalence_candidate["mismatch_count"],
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "distinct_keys", "current_mappable", "candidate_mappable",
        "positives", "negatives", "regressions", "new_ambiguity", "verdict")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
