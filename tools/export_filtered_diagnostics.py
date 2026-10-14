"""Export rejected alignments as clearly marked, non-publishable TextGrid/WAV pairs."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import wave
from pathlib import Path

from japanmfa.domain import Mora, PhoneAnnotation, PhoneInterval, Token
from japanmfa.mfa.textgrid import MfaWord
from japanmfa.output.textgrid import build_word_intervals, write_five_tier_textgrid
from tools.audit_textgrid_pauses import audit


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _artifact_for(row: dict, repo_root: Path) -> tuple[Path, dict]:
    reason = row.get("reason_code")
    for attempt in reversed(row.get("attempts", [])):
        if attempt.get("status") != "failed" or attempt.get("reason_code") != reason:
            continue
        run = Path(str(attempt["run"]))
        if not run.is_absolute():
            run = repo_root / run
        artifact = run / "pipeline" / str(row["stem"])
        required = ("frontend.json", "mfa.json", "postprocess.json", "work/audio.wav")
        if all((artifact / name).is_file() for name in required):
            return artifact, attempt
    raise ValueError(f"no complete failed artifact matches {row['stem']}: {reason}")


def _annotations(rows: list[dict]) -> tuple[PhoneAnnotation, ...]:
    return tuple(
        PhoneAnnotation(
            PhoneInterval(float(row["start"]), float(row["end"]), str(row["label"])),
            row.get("token_index"),
            tuple(Mora(**mora) for mora in row.get("morae", [])),
            str(row.get("kana", "")),
            str(row.get("tone", "")),
            bool(row["silence"]),
        )
        for row in rows
    )


def _duration(path: Path) -> float:
    with wave.open(str(path), "rb") as stream:
        return stream.getnframes() / stream.getframerate()


def export(report_path: Path, filtered_index_path: Path, output: Path, repo_root: Path) -> dict:
    report = _read(report_path)
    filtered_index = _read(filtered_index_path)
    failed = {str(row["stem"]): row for row in report["results"] if not row["published"]}
    selected = [str(item["stem"]) for item in filtered_index["items"]]
    if len(selected) != filtered_index["count"] or len(selected) != len(set(selected)):
        raise ValueError("filtered index count or uniqueness is invalid")
    if set(selected) != set(failed):
        raise ValueError("filtered index and report failed samples differ")
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"diagnostic output must be absent or empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    (output / "NOT_FOR_PUBLICATION.txt").write_text(
        "These TextGrids are rejected pipeline candidates for visual diagnosis only.\n"
        "They are not validated MFA deliverables. Use the same-stem .wav as the paired audio.\n",
        encoding="utf-8",
    )

    results: list[dict] = []
    for stem in selected:
        row = failed[stem]
        artifact, attempt = _artifact_for(row, repo_root)
        frontend = _read(artifact / "frontend.json")
        mfa = _read(artifact / "mfa.json")
        postprocess = _read(artifact / "postprocess.json")
        if postprocess.get("passed") is not False or postprocess.get("reason_code") != row.get("reason_code"):
            raise ValueError(f"failed artifact status differs from report: {stem}")
        annotations = _annotations(postprocess["final_phones"])
        tokens = tuple(Token(**token) for token in frontend["tokens"])
        aliases = tuple(str(alias) for alias in mfa["aliases"])
        if len(tokens) != len(aliases):
            raise ValueError(f"token/alias count differs: {stem}")
        aligned_words: list[MfaWord] = []
        for token, alias in zip(tokens, aliases):
            owned = [item.interval for item in annotations
                     if not item.is_silence and item.token_index == token.index]
            if not owned:
                raise ValueError(f"token has no final phone owner: {stem}: {token.index}")
            aligned_words.append(MfaWord(alias, min(item.start for item in owned),
                                         max(item.end for item in owned)))

        filtered_dir = Path(str(row["filtered_output"]))
        source_audio = filtered_dir / "source.wav"
        work_audio = artifact / "work" / "audio.wav"
        if _sha256(source_audio) != _sha256(work_audio):
            raise ValueError(f"working and filtered WAV differ: {stem}")
        duration = _duration(source_audio)
        words, unplaced = build_word_intervals(
            duration, str(frontend["original"]), tokens, tuple(aligned_words), aliases,
            phone_annotations=annotations,
        )
        grid = output / f"{stem}.TextGrid"
        audio = output / f"{stem}.wav"
        write_five_tier_textgrid(
            grid, duration, "<sp1>" + str(frontend["original"]),
            "<sp1>" + str(frontend["kana"]), annotations, words=words,
        )
        shutil.copy2(source_audio, audio)
        check = audit(grid)
        diagnostic = {
            "stem": stem,
            "reason_code": row.get("reason_code"),
            "source_artifact": str(artifact),
            "attempt": attempt,
            "textgrid": grid.name,
            "wav": audio.name,
            "textgrid_sha256": _sha256(grid),
            "wav_sha256": _sha256(audio),
            "suspect_pauses": postprocess.get("pause_acoustic_coverage", {}).get("suspect_pauses", []),
            "timestamp_alignment": postprocess.get("timestamp_alignment"),
            "raw_timestamp_alignment": postprocess.get("raw_timestamp_alignment"),
            "short_phone_issues": postprocess.get("short_phone_issues", []),
            "punctuation_unplaced": list(unplaced),
            "candidate_audit": check,
            "publication_status": "diagnostic_rejected_candidate",
        }
        _write(output / f"{stem}.diagnostic.json", diagnostic)
        results.append(diagnostic)

    payload = {
        "status": "NOT_FOR_PUBLICATION",
        "source_report": str(report_path.resolve()),
        "source_filtered_index": str(filtered_index_path.resolve()),
        "count": len(results),
        "items": results,
    }
    _write(output / "index.json", payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--filtered-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    payload = export(args.report, args.filtered_index, args.output, args.repo_root.resolve())
    print(json.dumps({"count": payload["count"], "output": str(args.output.resolve())},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
