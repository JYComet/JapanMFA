#!/usr/bin/env python3
"""Re-check items filtered with ``no_mappable_pronunciation`` against a candidate map.

Reads the real per-item source text, re-runs the real frontend to recover the
locked readings, looks the readings up in the production per-word G2P cache
(under the job's own adapter identity), and replays the production gate
``projection.filter_mappable_pronunciations`` twice - once with the bundled map
and once with the candidate map.

An item counts as **fixed** when the bundled map still raises
``no_mappable_pronunciation`` and the candidate map lets every token through.
This exercises the exact code path and the exact cached G2P results the running
job used; nothing is written except the report.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import random
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

from japanmfa.cache import stage_fingerprint  # noqa: E402
from japanmfa.config import PipelineConfig  # noqa: E402
from japanmfa.corpus import load_source_text  # noqa: E402
from japanmfa.domain import Pronunciation, Token  # noqa: E402
from japanmfa.errors import StageFailure  # noqa: E402
from japanmfa.frontend.japanese import JapaneseFrontend  # noqa: E402
from japanmfa.frontend.mora import segment_morae  # noqa: E402
from japanmfa.mfa.g2p import MfaG2pClient, TerminalSokuonG2p  # noqa: E402
from japanmfa.mfa.phone_map import PhoneMap  # noqa: E402
from japanmfa.pipeline import _adapter_id  # noqa: E402
from japanmfa.projection import filter_mappable_pronunciations  # noqa: E402

DEFAULT_MAP = REPO / "src/japanmfa/mfa/data/japanese_mfa_v3_phone_map.yaml"


def _g2p_identity(config: PipelineConfig, model_root: Path) -> str | None:
    """Reproduce the per-word G2P cache identity the job wrote under.

    Best effort only: the identity hashes the adapter *and* the source files, so
    if ``g2p.py`` changed after the job started the recomputation no longer
    matches.  The caller falls back to the most recently written identity, which
    is the one the still-running job keeps appending to.
    """
    try:
        g2p = TerminalSokuonG2p(MfaG2pClient(config.commands.mfa, config.mfa.g2p_model))
        return stage_fingerprint("native-g2p-word-v1", {
            "adapter": _adapter_id(g2p),
            "model": config.mfa.g2p_model,
            "archive": model_root / "pretrained_models/g2p" / (config.mfa.g2p_model + ".zip"),
            "implementation": REPO / "src/japanmfa/mfa/g2p.py",
            "resident": REPO / "src/japanmfa/mfa/native_resident.py",
        })
    except Exception:
        return None


def _load_word_cache(path: Path) -> tuple[dict, dict, str]:
    """Read every g2p payload: ({identity: {reading: payload}}, counts, newest_id)."""
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    rows = connection.execute(
        "SELECT identity, request, payload FROM words WHERE stage='g2p'").fetchall()
    newest = connection.execute(
        "SELECT identity FROM words WHERE stage='g2p' GROUP BY identity "
        "ORDER BY MAX(rowid) DESC LIMIT 1").fetchone()
    connection.close()
    by_identity: dict[str, dict] = collections.defaultdict(dict)
    for identity, request, payload in rows:
        by_identity[identity][json.loads(request)] = json.loads(payload)
    counts = {identity: len(entries) for identity, entries in by_identity.items()}
    return by_identity, counts, (newest[0] if newest else "")


def _gate(tokens, readings_to_payload, phone_map):
    """Run the production gate; return (ok, reason, detail)."""
    pronunciations = []
    for token in tokens:
        payload = readings_to_payload.get(token.reading)
        if payload is None:
            return False, "g2p_cache_miss", token.reading
        pronunciations.append(Pronunciation(
            token.reading, tuple(payload["phones"]),
            tuple(tuple(v) for v in payload.get("alternates", []))))
    token_morae = {token.index: segment_morae(token) for token in tokens}
    try:
        filter_mappable_pronunciations(tokens, tuple(pronunciations), token_morae, phone_map)
    except StageFailure as exc:
        return False, exc.reason_code, exc.details.get("reading")
    return True, None, None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--progress", type=Path, required=True,
                        help="the job's progress.sqlite3")
    parser.add_argument("--word-cache", type=Path, required=True,
                        help="the job's native-words.sqlite3")
    parser.add_argument("--source-root", type=Path, default=Path("/mnt/Raw/JapGalgame"))
    parser.add_argument("--reason", default="no_mappable_pronunciation")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--sample", type=int, default=None,
                        help="random subset of this size (fixed seed), spread across all games")
    parser.add_argument("--seed", type=int, default=20261008)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    config = PipelineConfig.load(args.config)
    model_root = Path(os.environ.get("MFA_ROOT_DIR", "/nonexistent"))
    identity = _g2p_identity(config, model_root)
    by_identity, counts, newest = _load_word_cache(args.word_cache)
    if identity is not None and identity in by_identity:
        words = by_identity[identity]
        identity_status = "matched_recomputed_identity"
    else:
        # g2p.py changed after the job started, so the recomputed identity no
        # longer matches; the job's is the one still being appended to.
        words = by_identity[newest]
        identity_status = f"using_newest_identity({newest[:12]})"

    current = PhoneMap.load(args.map)
    candidate = PhoneMap.load(args.candidate)
    frontend = JapaneseFrontend()

    connection = sqlite3.connect(f"file:{args.progress}?mode=ro", uri=True)
    keys = [row[0] for row in connection.execute(
        "SELECT key FROM items WHERE reason=? ORDER BY key", (args.reason,))]
    connection.close()
    if args.limit:
        keys = keys[:args.limit]
    if args.sample and args.sample < len(keys):
        keys = sorted(random.Random(args.seed).sample(keys, args.sample))

    tally = collections.Counter()
    fixed: list[dict] = []
    still_failing: list[dict] = []
    residual: collections.Counter = collections.Counter()
    residual_by_reading: collections.Counter = collections.Counter()
    for key in keys:
        game, _, stem = key.partition("/")
        source_path = args.source_root / game / "txt" / f"{stem}.txt"
        if not source_path.is_file():
            tally["source_missing"] += 1
            continue
        try:
            tokens = frontend.analyze(load_source_text(source_path))
        except Exception:
            tally["frontend_failed"] += 1
            continue
        before_ok, before_reason, before_reading = _gate(tokens, words, current)
        if before_ok:
            tally["already_ok_now"] += 1
            continue
        after_ok, after_reason, after_reading = _gate(tokens, words, candidate)
        record = {"key": key, "tokens": len(tokens),
                  "before_reason": before_reason, "before_reading": before_reading}
        if after_ok:
            tally["fixed"] += 1
            fixed.append(record)
        else:
            tally["still_failing"] += 1
            record["after_reason"] = after_reason
            record["after_reading"] = after_reading
            still_failing.append(record)
            reading = after_reading or ""
            residual_by_reading[(reading, after_reason)] += 1
            if after_reason == "g2p_cache_miss":
                residual["g2p_cache_miss"] += 1
            elif "ッ" in reading:
                residual["still_fails_sokuon(促音)"] += 1
            elif "ー" in reading:
                residual["still_fails_long_vowel(ー)"] += 1
            else:
                residual[f"still_fails_other:{after_reason}"] += 1

    report = {
        "reason": args.reason,
        "identity_status": identity_status,
        "identity_counts": counts,
        "identity_used": newest if "newest" in identity_status else identity,
        "items_checked": len(keys),
        "tally": dict(tally),
        "residual_categories": dict(residual.most_common()),
        "residual_top_readings": [
            {"reading": reading, "reason": reason, "items": count}
            for (reading, reason), count in residual_by_reading.most_common(500)],
        "fixed_samples": fixed[:30],
        "still_failing_samples": still_failing[:60],
        "fixed_rate": (tally["fixed"] / len(keys)) if keys else None,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in
                      ("identity_status", "items_checked", "tally", "fixed_rate")},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
