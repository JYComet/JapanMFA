from __future__ import annotations

import json
import inspect
from pathlib import Path

from typer.testing import CliRunner

from japanmfa.cli import app
from japanmfa.checks import PreflightCheck, PreflightReport, run_preflight
from japanmfa.errors import StageFailure


runner = CliRunner()


def test_public_cli_help_renders_without_typer_click_errors() -> None:
    for arguments in (["--help"], ["run", "--help"], ["run-file", "--help"]):
        result = runner.invoke(app, arguments)

        assert result.exit_code == 0, result.exception
        assert "Usage:" in result.output


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
    output = tmp_path.parent / f"{tmp_path.name}-output"

    class FakeResult:
        summary_path = output / "summary.json"
        summary = {"counts": {"aligned": 1, "failed": 0, "skipped": 0}}

    class FakePipeline:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, input_root, output_root, override_path):
            assert Path(input_root) != audio.parent
            return FakeResult()

    monkeypatch.setattr("japanmfa.cli.JapanMFAPipeline", FakePipeline)
    before = sorted(path.name for path in tmp_path.iterdir())
    result = runner.invoke(app, ["run-file", str(audio), "--text", str(text), "--output", str(output), "--config", str(config)])
    after = sorted(path.name for path in tmp_path.iterdir())
    assert result.exit_code == 0
    assert before == after


def test_run_file_rejects_output_nested_in_original_audio_directory_before_copy(tmp_path: Path, monkeypatch) -> None:
    audio = tmp_path / "one.wav"
    audio.write_bytes(b"wav")
    config = tmp_path / "config.yaml"
    _config(config)

    def fail_copy(*_args, **_kwargs):
        raise AssertionError("copy must not run before path validation")

    monkeypatch.setattr("japanmfa.cli.shutil.copy2", fail_copy)
    result = runner.invoke(app, ["run-file", str(audio), "--output", str(tmp_path / "out"), "--config", str(config)])

    assert result.exit_code == 1
    assert "input corpus" in result.output.lower()


def test_run_file_uses_resolved_symlink_target_parent_for_path_safety(tmp_path: Path, monkeypatch) -> None:
    real_source = tmp_path / "real-source"
    link_source = tmp_path / "link-source"
    real_source.mkdir()
    link_source.mkdir()
    target = real_source / "target.wav"
    target.write_bytes(b"wav")
    audio = link_source / "linked.wav"
    audio.symlink_to(target)
    config = tmp_path / "config.yaml"
    _config(config)

    def fail_copy(*_args, **_kwargs):
        raise AssertionError("copy must not run before resolved-target validation")

    monkeypatch.setattr("japanmfa.cli.shutil.copy2", fail_copy)
    result = runner.invoke(app, ["run-file", str(audio), "--output", str(real_source / "out"), "--config", str(config)])

    assert result.exit_code == 1
    assert "input corpus" in result.output.lower()


def test_run_converts_domain_setup_failure_to_controlled_cli_error(tmp_path: Path, monkeypatch) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    config = tmp_path / "config.yaml"
    _config(config)

    class BrokenPipeline:
        def __init__(self, *_args, **_kwargs):
            raise StageFailure("setup", "missing_model", "Japanese MFA model is unavailable")

    monkeypatch.setattr("japanmfa.cli.JapanMFAPipeline", BrokenPipeline)
    result = runner.invoke(app, ["run", "--input", str(corpus), "--output", str(tmp_path / "out"), "--config", str(config)])

    assert result.exit_code == 1
    assert "batch setup failure" in result.output.lower()
    assert "traceback" not in result.output.lower()


def test_check_prints_preflight_report_and_returns_success(
    tmp_path: Path, monkeypatch
) -> None:
    config = tmp_path / "config.yaml"
    _config(config)
    report = PreflightReport(
        ok=True,
        checks=(PreflightCheck("fake", True, "ok", "ready"),),
    )
    monkeypatch.setattr("japanmfa.checks.run_preflight", lambda _config: report)

    result = runner.invoke(app, ["check", "--config", str(config)])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == report.as_dict()
    assert list(inspect.signature(run_preflight).parameters) == ["config"]


def test_check_prints_failed_preflight_and_returns_nonzero(
    tmp_path: Path, monkeypatch
) -> None:
    config = tmp_path / "config.yaml"
    _config(config)
    report = PreflightReport(
        ok=False,
        checks=(PreflightCheck("fake", False, "model_unavailable", "missing", "download model"),),
    )
    monkeypatch.setattr("japanmfa.checks.run_preflight", lambda _config: report)

    result = runner.invoke(app, ["check", "--config", str(config)])

    assert result.exit_code == 1
    assert json.loads(result.stdout)["ok"] is False
    assert "model_unavailable" in result.stdout
