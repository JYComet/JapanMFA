from __future__ import annotations

import array
import json
import subprocess
import sys
import wave
from pathlib import Path


def _write_wave(path: Path) -> None:
    samples = array.array("h", [0] * 1600 + [4000] * 12800 + [0] * 1600)
    with wave.open(str(path), "wb") as stream:
        stream.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        stream.writeframes(samples.tobytes())


def test_cli_exports_same_stem_diagnostic_textgrid_and_wav(tmp_path: Path) -> None:
    stem = "sample_failed"
    run = tmp_path / "run"
    artifact = run / "pipeline" / stem
    work = artifact / "work"
    work.mkdir(parents=True)
    _write_wave(work / "audio.wav")
    (artifact / "frontend.json").write_text(json.dumps({
        "original": "あ", "kana": "ア",
        "tokens": [{"index": 0, "start": 0, "end": 1, "surface": "あ",
                    "part_of_speech": ["名詞"], "reading": "ア",
                    "reading_source": "test"}],
    }), encoding="utf-8")
    (artifact / "mfa.json").write_text(json.dumps({"aliases": ["jmfa_000000"]}), encoding="utf-8")
    speech = {"start": .1, "end": .9, "label": "a", "token_index": 0,
              "morae": [{"token_index": 0, "index_in_token": 0,
                           "kana": "ア", "tone": "H"}],
              "kana": "ア", "tone": "HH", "silence": False}
    (artifact / "postprocess.json").write_text(json.dumps({
        "passed": False, "reason_code": "alignment_acoustic_coverage",
        "final_phones": [speech], "raw_phones": [speech],
        "short_phone_issues": [],
        "pause_acoustic_coverage": {"suspect_pauses": [{
            "start": 0.0, "end": 0.1, "active_ranges": [[0.0, 0.1]],
        }]},
        "timestamp_alignment": {"issues": []},
    }), encoding="utf-8")

    filtered = tmp_path / "filtered" / stem
    filtered.mkdir(parents=True)
    _write_wave(filtered / "source.wav")
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"results": [{
        "stem": stem, "published": False,
        "reason_code": "alignment_acoustic_coverage",
        "attempts": [{"run": str(run), "status": "failed",
                      "reason_code": "alignment_acoustic_coverage"}],
        "filtered_output": str(filtered),
    }]}), encoding="utf-8")
    index = tmp_path / "filtered" / "index.json"
    index.write_text(json.dumps({"count": 1, "items": [{
        "stem": stem, "reason_code": "alignment_acoustic_coverage",
        "directory": str(filtered),
    }]}), encoding="utf-8")
    output = tmp_path / "diagnostic"

    completed = subprocess.run(
        [sys.executable, "tools/export_filtered_diagnostics.py",
         "--report", str(report), "--filtered-index", str(index),
         "--output", str(output), "--repo-root", str(Path.cwd())],
        cwd=Path.cwd(), text=True, capture_output=True, check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert (output / f"{stem}.TextGrid").is_file()
    assert (output / f"{stem}.wav").read_bytes() == (filtered / "source.wav").read_bytes()
    assert (output / "NOT_FOR_PUBLICATION.txt").is_file()
    result = json.loads((output / "index.json").read_text(encoding="utf-8"))
    assert result["count"] == 1
    assert result["items"][0]["reason_code"] == "alignment_acoustic_coverage"
    assert result["items"][0]["textgrid"] == f"{stem}.TextGrid"
    assert result["items"][0]["wav"] == f"{stem}.wav"
    assert result["items"][0]["suspect_pauses"][0]["start"] == 0.0
