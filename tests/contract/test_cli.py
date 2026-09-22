from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from japanmfa.cli import app


runner = CliRunner()


def _config(path: Path) -> None:
    path.write_text("asr:\n  language: Japanese\n", encoding="utf-8")


def test_run_rejects_identical_and_nested_output_roots(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    config = tmp_path / "config.yaml"
    _config(config)

    same = runner.invoke(app, ["run", "--input", str(corpus), "--output", str(corpus), "--config", str(config)])
    nested = runner.invoke(app, ["run", "--input", str(corpus), "--output", str(corpus / "out"), "--config", str(config)])
    assert same.exit_code != 0
    assert nested.exit_code != 0
    assert "output" in same.output.lower()


def test_inspect_prints_manifest_counts_without_writing(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.jsonl"
    rows = [
        {"status": "aligned"},
        {"status": "skipped"},
        {"status": "failed"},
        {"status": "aligned"},
    ]
    manifest.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    result = runner.invoke(app, ["inspect", str(manifest)])

    assert result.exit_code == 0
    assert "aligned: 2" in result.stdout
    assert "skipped: 1" in result.stdout
    assert "failed: 1" in result.stdout


def test_run_accepts_absolute_config_and_override_paths_and_batch_item_failures_are_successful(
    tmp_path: Path, monkeypatch
) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.wav").write_bytes(b"wav")
    output = tmp_path / "output"
    config = tmp_path / "config.yaml"
    overrides = tmp_path / "overrides.yaml"
    _config(config)
    overrides.write_text("utterances: {}\n", encoding="utf-8")

    class FakeResult:
        summary_path = output / "summary.json"
        outcomes = ()
        summary = {"counts": {"aligned": 0, "failed": 1, "skipped": 0}}

    class FakePipeline:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

        def run(self, input_root, output_root, override_path):
            assert Path(input_root) == corpus
            assert Path(output_root) == output
            assert Path(override_path) == overrides
            output.mkdir()
            FakeResult.summary_path.write_text("{}", encoding="utf-8")
            return FakeResult()

    monkeypatch.setattr("japanmfa.cli.JapanMFAPipeline", FakePipeline)
    result = runner.invoke(
        app,
        ["run", "--input", str(corpus), "--output", str(output), "--config", str(config), "--overrides", str(overrides)],
    )

    assert result.exit_code == 0
    assert "summary.json" in result.stdout


def test_run_file_does_not_modify_source_directory(tmp_path: Path, monkeypatch) -> None:
    audio = tmp_path / "one.wav"
    text = tmp_path / "one.txt"
    audio.write_bytes(b"wav")
    text.write_text("今日は晴れ", encoding="utf-8")
    config = tmp_path / "config.yaml"
    _config(config)

    class FakeResult:
        summary_path = tmp_path / "out" / "summary.json"
        summary = {"counts": {"aligned": 1, "failed": 0, "skipped": 0}}

    class FakePipeline:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, input_root, output_root, override_path):
            assert Path(input_root) != audio.parent
            return FakeResult()

    monkeypatch.setattr("japanmfa.cli.JapanMFAPipeline", FakePipeline)
    before = sorted(path.name for path in tmp_path.iterdir())
    result = runner.invoke(app, ["run-file", str(audio), "--text", str(text), "--output", str(tmp_path / "out"), "--config", str(config)])
    after = sorted(path.name for path in tmp_path.iterdir())
    assert result.exit_code == 0
    assert before == after
