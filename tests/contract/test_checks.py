from __future__ import annotations

import json
import hashlib
import inspect
import os
import re
import subprocess
import stat
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from japanmfa.checks import PreflightReport, _check, run_preflight
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
    if "FAKE_TD_OUTPUT" in __import__("os").environ:
        print(__import__("os").environ["FAKE_TD_OUTPUT"])
    elif __import__("os").environ.get("FAKE_TD_MODE", "valid") == "malformed":
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
    monkeypatch.setenv("FAKE_MFA_VERSION", "MFA version: 2.0.1")
    monkeypatch.setenv("JAPANMFA_SECRET_TOKEN", "secret-token")
    report = run_preflight(_config(tmp_path, fake))

    check = _names(report)["mfa_version"]
    assert not report.ok
    assert check.reason_code == "mfa_version_incompatible"
    assert "secret-token" not in report.to_json()


@pytest.mark.parametrize(
    "version_output",
    [
        "dependency 3.12.0\nMontreal Forced Aligner 2.0.1",
        "MFA version: 2.9.0",
    ],
)
def test_mfa_version_parser_does_not_accept_dependency_major_three(
    tmp_path: Path, monkeypatch, version_output: str
) -> None:
    fake = _fake(tmp_path)
    monkeypatch.setenv("FAKE_MFA_VERSION", version_output)

    report = run_preflight(_config(tmp_path, fake))

    assert _names(report)["mfa_version"].reason_code == "mfa_version_incompatible"


@pytest.mark.parametrize("version_output", ["3.3.9", "Montreal Forced Aligner version: 3.3.9"])
def test_mfa_version_parser_accepts_bare_or_product_version(
    tmp_path: Path, monkeypatch, version_output: str
) -> None:
    fake = _fake(tmp_path)
    monkeypatch.setenv("FAKE_MFA_VERSION", version_output)

    report = run_preflight(_config(tmp_path, fake))

    assert _names(report)["mfa_version"].ok


def test_preflight_redacts_sensitive_values_and_embedded_environment_secrets(
    tmp_path: Path, monkeypatch
) -> None:
    fake = _fake(tmp_path)
    monkeypatch.setenv("JAPANMFA_API_KEY", "embedded-api-secret")
    monkeypatch.setenv("FAKE_MFA_VERSION", "secret-token my_api_key_value")
    monkeypatch.setenv("JAPANMFA_TDMELODIC_COMMAND", f"{sys.executable} {fake} tdmelodic")
    report = run_preflight(_config(tmp_path, fake))
    rendered = report.to_json()

    assert "embedded-api-secret" not in rendered
    assert "secret-token" not in rendered
    assert "my_api_key_value" not in rendered
    assert "g2p" in rendered
    safe = _check(
        "redaction",
        False,
        "command_failed",
        "secret-token and embedded-api-secret",
        "retry with my_api_key_value",
        ["tool", "--token", "secret-token", "authorization_header"],
    )
    safe_rendered = json.dumps(safe.as_dict())
    assert "secret-token" not in safe_rendered
    assert "embedded-api-secret" not in safe_rendered
    assert "my_api_key_value" not in safe_rendered
    assert "authorization_header" not in safe_rendered
    monkeypatch.setenv("JAPANMFA_SECRET", "ak")
    ordinary = _check(
        "ordinary",
        False,
        "command_failed",
        "/tmp/tokenizer tokenization-model ACCESS_KEY=ak",
        "retry tokenizer",
        ["/tmp/tokenizer", "tokenization-model", "ACCESS_KEY=ak"],
    )
    ordinary_rendered = json.dumps(ordinary.as_dict())
    assert "tokenizer" in ordinary_rendered
    assert "tokenization-model" in ordinary_rendered
    assert "ak" not in ordinary_rendered
    embedded = _check(
        "embedded",
        False,
        "command_failed",
        "prefixak-suffix",
        "prefixak-suffix",
        ["prefixak-suffix"],
    )
    embedded_rendered = json.dumps(embedded.as_dict())
    assert "prefixak-suffix" not in embedded_rendered
    assert "ak" not in embedded_rendered


def test_generic_marker_secret_uses_boundaries_without_overredacting_names(
    monkeypatch,
) -> None:
    monkeypatch.setenv("JAPANMFA_SECRET", "token")
    safe = _check(
        "ordinary",
        False,
        "command_failed",
        "/tmp/tokenizer tokenization-model token",
        "retry tokenization-model",
        ["/tmp/tokenizer", "tokenization-model", "token"],
    )

    rendered = json.dumps(safe.as_dict())
    assert "/tmp/tokenizer" in rendered
    assert "tokenization-model" in rendered
    assert '"token"' not in rendered


def test_readme_wrapper_example_is_complete_and_copyable() -> None:
    readme = (Path(__file__).parents[2] / "README.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```bash\n(.*?)```", readme, flags=re.DOTALL)
    build_blocks = [block for block in blocks if "build_tdmelodic_image.sh" in block]

    assert build_blocks
    assert all(
        all(name in block for name in ("TDMELODIC_COMMIT", "TDMELODIC_UNIDIC_ARCHIVE", "TDMELODIC_UNIDIC_SHA256"))
        for block in build_blocks
    )


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


@pytest.mark.parametrize("output", ["[[ニホンゴ]]", "][ニホンゴ]["])
def test_tdmelodic_probe_rejects_malformed_brackets(
    tmp_path: Path, monkeypatch, output: str
) -> None:
    fake = _fake(tmp_path)
    monkeypatch.setenv("FAKE_TD_OUTPUT", output)
    monkeypatch.setenv("JAPANMFA_TDMELODIC_COMMAND", f"{sys.executable} {fake} tdmelodic")

    report = run_preflight(_config(tmp_path, fake))

    assert _names(report)["tdmelodic_probe"].reason_code == "probe_malformed"


def test_run_preflight_signature_is_stable() -> None:
    assert list(inspect.signature(run_preflight).parameters) == ["config"]


def test_tdmelodic_wrapper_executes_docker_with_immutable_commit(tmp_path: Path) -> None:
    fake_docker = tmp_path / "docker"
    argv_file = tmp_path / "docker-argv"
    fake_docker.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, pathlib, sys\n"
        "context = pathlib.Path(sys.argv[-1])\n"
        "payload = {'argv': sys.argv[1:], 'context': str(context), 'context_exists': context.is_dir(), 'files': sorted(p.name for p in context.iterdir())}\n"
        "pathlib.Path(os.environ['FAKE_DOCKER_ARGV']).write_text(json.dumps(payload))\n",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    archive = tmp_path / "unidic.zip"
    archive.write_bytes(b"fake-unidic-archive")
    archive_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    commit = "0123456789abcdef" * 2 + "01234567"
    env = {
        **os.environ,
        "DOCKER_BIN": str(fake_docker),
        "FAKE_DOCKER_ARGV": str(argv_file),
        "TDMELODIC_COMMIT": commit,
        "TDMELODIC_UNIDIC_ARCHIVE": str(archive),
        "TDMELODIC_UNIDIC_SHA256": archive_sha,
    }

    subprocess.run(
        [str(Path(__file__).parents[2] / "tools" / "build_tdmelodic_image.sh")],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    payload = json.loads(argv_file.read_text(encoding="utf-8"))
    argv = payload["argv"]
    assert argv[0:2] == ["build", "--build-arg"]
    assert f"TDMELODIC_COMMIT={commit}" in argv
    assert "--file" in argv
    assert any(item.endswith("Dockerfile.tdmelodic") for item in argv)
    assert payload["context_exists"] is True
    assert "Dockerfile.tdmelodic" in payload["files"]
    assert "unidic-mecab_kana-accent-2.1.2_src.zip" in payload["files"]
    assert not Path(payload["context"]).exists()


def test_tdmelodic_wrapper_rejects_empty_or_mutable_commit(tmp_path: Path) -> None:
    wrapper = Path(__file__).parents[2] / "tools" / "build_tdmelodic_image.sh"
    for commit in ("", "main", "release/latest", "deadbeef"):
        result = subprocess.run(
            [str(wrapper)],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "TDMELODIC_COMMIT": commit},
        )
        assert result.returncode != 0


@pytest.mark.parametrize("mode", ["missing_archive", "missing_hash", "wrong_hash", "symlink_archive"])
def test_tdmelodic_wrapper_rejects_unidic_archive_preconditions(
    tmp_path: Path, mode: str
) -> None:
    wrapper = Path(__file__).parents[2] / "tools" / "build_tdmelodic_image.sh"
    archive = tmp_path / "unidic.zip"
    archive.write_bytes(b"fake-unidic-archive")
    archive_value = archive
    if mode == "symlink_archive":
        link = tmp_path / "unidic-link.zip"
        link.symlink_to(archive)
        archive_value = link
    env = {
        **os.environ,
        "TDMELODIC_COMMIT": "0123456789abcdef" * 2 + "01234567",
        "TDMELODIC_UNIDIC_ARCHIVE": str(archive_value),
        "TDMELODIC_UNIDIC_SHA256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "DOCKER_BIN": str(tmp_path / "docker-that-must-not-run"),
    }
    if mode == "missing_archive":
        env["TDMELODIC_UNIDIC_ARCHIVE"] = str(tmp_path / "missing.zip")
    elif mode == "missing_hash":
        env["TDMELODIC_UNIDIC_SHA256"] = ""
    elif mode == "wrong_hash":
        env["TDMELODIC_UNIDIC_SHA256"] = "0" * 64

    result = subprocess.run([str(wrapper)], check=False, capture_output=True, text=True, env=env)

    assert result.returncode != 0


def test_tdmelodic_dockerfile_checks_upstream_and_immutable_commit() -> None:
    dockerfile = (Path(__file__).parents[2] / "tools" / "Dockerfile.tdmelodic").read_text(
        encoding="utf-8"
    )
    assert "ARG TDMELODIC_REPOSITORY" in dockerfile
    assert "ARG TDMELODIC_COMMIT" in dockerfile
    assert "git clone" in dockerfile
    assert "git checkout --detach" in dockerfile
    assert "mecab-config" in dockerfile
    assert "unidic-mecab_kana-accent-2.1.2_src.zip" in dockerfile
    assert "build-essential" in dockerfile
    assert "configure" in dockerfile
    assert "make install" in dockerfile
    assert 'ENTRYPOINT ["tdmelodic-sy2a"]' in dockerfile


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
