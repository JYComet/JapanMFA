import json
from pathlib import Path

import pytest

from japanmfa.domain import UtteranceOutcome
from japanmfa.output.reports import append_manifest, summarize, write_json


def test_write_json_is_unicode_sorted_atomic_and_secret_safe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "nested" / "report.json"
    monkeypatch.setenv("OPENAI_API_KEY", "do-not-write-this-secret")

    write_json(
        path,
        {"z": "日本語", "a": 1, "credentials": {"api_key": "do-not-write-this-secret"}},
    )

    raw = path.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    assert raw.index('"a"') < raw.index('"z"')
    assert "日本語" in raw
    assert "do-not-write-this-secret" not in raw
    assert json.loads(raw)["a"] == 1


def test_manifest_and_summary_group_outcomes_stably(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.jsonl"
    outcomes = (
        UtteranceOutcome("u1", "aligned", None, None, tmp_path / "output" / "u1", {"mfa": 0.2}),
        UtteranceOutcome("u2", "skipped", "unsupported_language", "skip", None, {}),
        UtteranceOutcome("u3", "failed", "mfa_failed", "fail", tmp_path / "output" / "u3", {"mfa": 0.4}),
        UtteranceOutcome("u4", "failed", "mfa_failed", "fail", None, {}),
    )
    for outcome in outcomes:
        append_manifest(manifest, outcome)

    lines = manifest.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4
    assert all("run_id" in json.loads(line) for line in lines)
    assert json.loads(lines[0])["artifact_dir"] == "output/u1"
    assert summarize(outcomes) == {
        "total": 4,
        "counts": {"aligned": 1, "failed": 2, "skipped": 1},
        "reasons": {
            "failed": {"mfa_failed": 2},
            "skipped": {"unsupported_language": 1},
        },
    }


def test_manifest_rejects_malformed_outcome(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="reason_code"):
        append_manifest(
            tmp_path / "manifest.jsonl",
            UtteranceOutcome("u", "failed", None, "missing reason", None, {}),
        )
