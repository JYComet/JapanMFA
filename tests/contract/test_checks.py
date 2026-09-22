from __future__ import annotations

import json
import stat
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from japanmfa.checks import PreflightReport, run_preflight
from japanmfa.config import CommandConfig, PathConfig, PipelineConfig


FAKE_CHECK = r'''
#!/usr/bin/env python3
import sys

args = sys.argv[1:]
if "-c" in args:
    code = " ".join(args)
    if "cuda.is_available" in code:
        print(__import__("os").environ.get("FAKE_CUDA", "1"))
    else:
        print("qwen_asr 0.1.0")
    raise SystemExit(0)
if args and args[0] == "mfa":
    args = args[1:]
if args == ["version"]:
    print(__import__("os").environ.get("FAKE_MFA_VERSION", "3.3.9"))
elif args[:2] == ["model", "inspect"]:
    if __import__("os").environ.get("FAKE_MFA_MODELS", "present") == "missing":
        print("model is not installed", file=sys.stderr)
        raise SystemExit(2)
    print("model present")
elif len(args) >= 2 and args[1] == "--help":
    print("Usage: fake")
elif args and args[0] == "tdmelodic":
    data = sys.stdin.read().strip()
    if __import__("os").environ.get("FAKE_TD_MODE", "valid") == "malformed":
        print("not-the-requested-reading")
    else:
        print(data.rsplit(",", 1)[-1])
elif args and args[0] == "asr-runtime":
    if "cuda.is_available" in " ".join(args):
        print(__import__("os").environ.get("FAKE_CUDA", "1"))
    else:
        print("qwen_asr 0.1.0")
'''


def _fake(tmp_path: Path) -> Path:
    path = tmp_path / "fake-check.py"
    path.write_text(FAKE_CHECK.lstrip(), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _config(tmp_path: Path, fake: Path) -> PipelineConfig:
    return replace(
        PipelineConfig(),
        commands=CommandConfig(
            ffmpeg=(sys.executable, "-c", "pass"),
            asr_worker=(str(fake),),
            mfa=(sys.executable, str(fake), "mfa"),
        ),
        paths=PathConfig(cache_dir=tmp_path / "cache", output_dir=tmp_path / "output"),
    )


def _names(report: PreflightReport) -> dict[str, object]:
    return {item.name: item for item in report.checks}


def test_missing_mfa_executable_is_actionable(tmp_path: Path) -> None:
    config = replace(
        PipelineConfig(),
        commands=CommandConfig(mfa=(str(tmp_path / "does-not-exist"),)),
        paths=PathConfig(cache_dir=tmp_path / "cache", output_dir=tmp_path / "output"),
    )

    report = run_preflight(config)

    assert not report.ok
    check = _names(report)["mfa_version"]
    assert check.reason_code == "executable_missing"
    assert check.action and "mfa" in check.action


def test_wrong_mfa_major_version_fails_without_leaking_output(tmp_path: Path, monkeypatch) -> None:
    fake = _fake(tmp_path)
    monkeypatch.setenv("FAKE_MFA_VERSION", "2.0.1 secret-token")
    report = run_preflight(_config(tmp_path, fake))

    check = _names(report)["mfa_version"]
    assert not report.ok
    assert check.reason_code == "mfa_version_incompatible"
    assert "secret-token" not in report.to_json()


def test_absent_japanese_models_are_reported_separately(tmp_path: Path, monkeypatch) -> None:
    fake = _fake(tmp_path)
    monkeypatch.setenv("FAKE_MFA_MODELS", "missing")
    report = run_preflight(_config(tmp_path, fake))

    names = _names(report)
    assert not report.ok
    assert names["mfa_acoustic_model"].reason_code == "model_unavailable"
    assert names["mfa_g2p_model"].reason_code == "model_unavailable"


@pytest.mark.parametrize("which", ["output", "cache"])
def test_unwritable_runtime_path_is_reported(tmp_path: Path, which: str) -> None:
    fake = _fake(tmp_path)
    output = tmp_path / "output-file"
    output.write_text("not a directory", encoding="utf-8")
    cache = tmp_path / "cache"
    cache.write_text("not a directory", encoding="utf-8")
    paths = PathConfig(
        cache_dir=cache if which == "cache" else tmp_path / "cache-ok",
        output_dir=output if which == "output" else tmp_path / "output-ok",
    )
    config = replace(_config(tmp_path, fake), paths=paths)

    report = run_preflight(config)

    assert not report.ok
    assert _names(report)[f"{which}_writable"].reason_code == "path_not_writable"


def test_cuda_unavailable_fails_only_when_cpu_is_explicitly_disallowed(
    tmp_path: Path, monkeypatch
) -> None:
    fake = _fake(tmp_path)
    monkeypatch.setenv("FAKE_CUDA", "0")
    monkeypatch.setenv("JAPANMFA_REQUIRE_CUDA", "1")
    report = run_preflight(_config(tmp_path, fake))

    check = _names(report)["qwen_cuda"]
    assert not report.ok
    assert check.reason_code == "cuda_unavailable"
    assert "install" in check.action.lower() or "cpu" in check.action.lower()


def test_malformed_tdmelodic_probe_is_typed(tmp_path: Path, monkeypatch) -> None:
    fake = _fake(tmp_path)
    monkeypatch.setenv("JAPANMFA_TDMELODIC_COMMAND", f"{sys.executable} {fake} tdmelodic")
    monkeypatch.setenv("FAKE_TD_MODE", "malformed")
    report = run_preflight(_config(tmp_path, fake))

    check = _names(report)["tdmelodic_probe"]
    assert not report.ok
    assert check.reason_code == "probe_malformed"


def test_valid_setup_has_individual_passes_and_json_contract(tmp_path: Path, monkeypatch) -> None:
    fake = _fake(tmp_path)
    model = tmp_path / "qwen-model"
    model.mkdir()
    monkeypatch.setenv("JAPANMFA_ASR_MODEL_PATH", str(model))
    monkeypatch.setenv("JAPANMFA_TDMELODIC_COMMAND", f"{sys.executable} {fake} tdmelodic")
    monkeypatch.delenv("JAPANMFA_REQUIRE_CUDA", raising=False)

    report = run_preflight(_config(tmp_path, fake))

    assert report.ok
    assert all(item.ok for item in report.checks)
    encoded = json.loads(report.to_json())
    assert encoded["ok"] is True
    assert all(item["command"] is None or isinstance(item["command"], list) for item in encoded["checks"])
    assert "JAPANMFA_ASR_MODEL_PATH" not in report.to_json()
