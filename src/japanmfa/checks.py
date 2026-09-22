"""Bounded, non-mutating runtime and model checks for ``japanmfa check``.

The orchestrator deliberately does not import Qwen, MFA, or tdmelodic.  This
module probes the configured isolated commands and returns a serialisable
report instead of raising an implementation-specific subprocess exception.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import tempfile
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from .accent.parser import parse_accent
from .config import PipelineConfig
from .domain import Token
from .frontend.mora import segment_morae


_BARE_VERSION_RE = re.compile(r"^\s*v?(\d+\.\d+(?:\.\d+)?)\s*$")
_MFA_PRODUCT_VERSION_RE = re.compile(
    r"^\s*(?:Montreal\s+Forced\s+Aligner|MFA)\b.*?v?(\d+\.\d+(?:\.\d+)?)\s*$",
    re.IGNORECASE,
)
_DEFAULT_TIMEOUT = 8.0
_PROBE_SURFACE = "日本語"
_PROBE_YOMI = "ニホンゴ"
_SENSITIVE_MARKER_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:access[_-]?key|access[_-]?token|api[_-]?key|"
    r"authorization|credential|private[_-]?key|password|secret|token|auth)"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_SENSITIVE_ENV_MARKERS = frozenset(
    {
        "accesskey",
        "accesstoken",
        "apikey",
        "authorization",
        "auth",
        "credential",
        "password",
        "privatekey",
        "secret",
        "token",
    }
)
_GENERIC_SECRET_VALUES = frozenset(
    {
        "accesskey",
        "accesstoken",
        "apikey",
        "auth",
        "authorization",
        "credential",
        "key",
        "password",
        "privatekey",
        "secret",
        "token",
    }
)


@dataclass(frozen=True)
class PreflightCheck:
    """One safe, actionable preflight result."""

    name: str
    ok: bool
    reason_code: str
    message: str
    action: str = ""
    command: tuple[str, ...] | None = None

    def as_dict(self) -> dict[str, object]:
        values = asdict(self)
        values["command"] = None if self.command is None else list(self.command)
        return values


@dataclass(frozen=True)
class PreflightReport:
    """Complete result of :func:`run_preflight`."""

    ok: bool
    checks: tuple[PreflightCheck, ...]

    def as_dict(self) -> dict[str, object]:
        return {"ok": self.ok, "checks": [check.as_dict() for check in self.checks]}

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, sort_keys=True)


def _display_command(command: Sequence[str] | None) -> tuple[str, ...] | None:
    """Return a command safe to include in a report.

    Commands are configured as argv arrays, but a user may still include a
    value-looking argument.  Redact arguments following common secret flags.
    """

    if command is None:
        return None
    result: list[str] = []
    redact_next = False
    for arg in command:
        text = _redact_text(str(arg))
        lowered = text.lower().lstrip("-")
        if redact_next:
            result.append("<redacted>")
            redact_next = False
            continue
        if _has_sensitive_marker(text):
            if "=" in text:
                result.append(text.split("=", 1)[0] + "=<redacted>")
            elif text.startswith("-"):
                result.append(text)
                redact_next = True
            else:
                result.append("<redacted>")
        else:
            result.append(text)
    return tuple(result)


def _redact_text(value: str) -> str:
    """Redact environment secrets and value-like secret tokens in text."""

    for key, secret in os.environ.items():
        normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
        if not secret or not any(marker in normalized for marker in _SENSITIVE_ENV_MARKERS):
            continue
        normalized_secret = re.sub(r"[^a-z0-9]", "", secret.casefold())
        if normalized_secret in _GENERIC_SECRET_VALUES:
            value = re.sub(
                rf"(?<![A-Za-z0-9]){re.escape(secret)}(?![A-Za-z0-9])",
                "[REDACTED]",
                value,
            )
        else:
            value = value.replace(secret, "[REDACTED]")
    if value.lstrip().startswith("-") and _has_sensitive_marker(value):
        if "=" in value:
            return value.split("=", 1)[0] + "=<redacted>"
        return value
    pieces = re.split(r"(\s+)", value)
    for index, piece in enumerate(pieces):
        if not piece or piece.isspace() or not _has_sensitive_marker(piece):
            continue
        if "=" in piece:
            pieces[index] = piece.split("=", 1)[0] + "=<redacted>"
        else:
            pieces[index] = "[REDACTED]"
    return "".join(pieces)


def _has_sensitive_marker(value: str) -> bool:
    return _SENSITIVE_MARKER_RE.search(value) is not None


def _check(
    name: str,
    ok: bool,
    reason_code: str,
    message: str,
    action: str = "",
    command: Sequence[str] | None = None,
) -> PreflightCheck:
    return PreflightCheck(
        name=name,
        ok=ok,
        reason_code=reason_code,
        message=_redact_text(message),
        action=_redact_text(action),
        command=_display_command(command),
    )


def _run(
    command: Sequence[str], *, input_text: str | None = None, timeout: float = _DEFAULT_TIMEOUT
) -> tuple[str, str, int | None, str | None]:
    """Run one argv command and return output without exposing it to callers."""

    try:
        completed = subprocess.run(
            list(command),
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            timeout=timeout,
        )
    except FileNotFoundError:
        return "", "", None, "executable_missing"
    except subprocess.TimeoutExpired:
        return "", "", None, "timeout"
    except OSError:
        return "", "", None, "command_error"
    return completed.stdout, completed.stderr, completed.returncode, None


def _mfa_version(config: PipelineConfig, timeout: float) -> PreflightCheck:
    command = (*config.commands.mfa, "version")
    stdout, _stderr, returncode, error = _run(command, timeout=timeout)
    if error == "executable_missing":
        return _check(
            "mfa_version",
            False,
            "executable_missing",
            "configured MFA executable could not be started",
            "Activate the MFA environment and verify `mfa version` works.",
            command,
        )
    if error == "timeout":
        return _check(
            "mfa_version", False, "command_timeout", "MFA version probe timed out", "Retry after checking the MFA environment.", command
        )
    if returncode != 0:
        return _check(
            "mfa_version", False, "command_failed", "MFA version probe failed", "Run `mfa version` in the configured MFA environment.", command
        )
    product_version: re.Match[str] | None = None
    bare_versions: list[re.Match[str]] = []
    for line in stdout.splitlines():
        product_match = _MFA_PRODUCT_VERSION_RE.fullmatch(line)
        if product_match is not None:
            product_version = product_match
            continue
        bare_match = _BARE_VERSION_RE.fullmatch(line)
        if bare_match is not None:
            bare_versions.append(bare_match)
    match = product_version or (bare_versions[0] if len(bare_versions) == 1 else None)
    if match is None:
        return _check(
            "mfa_version", False, "mfa_version_unparseable", "MFA did not report a semantic version", "Run `mfa version` and inspect the configured executable.", command
        )
    if int(match.group(1).split(".", 1)[0]) != 3:
        return _check(
            "mfa_version", False, "mfa_version_incompatible", "MFA major version must be 3", "Install Montreal Forced Aligner 3.x in the isolated MFA environment.", command
        )
    return _check("mfa_version", True, "ok", "MFA 3.x detected", command=command)


def _mfa_help(config: PipelineConfig, timeout: float) -> PreflightCheck:
    commands = tuple((*config.commands.mfa, subcommand, "--help") for subcommand in ("g2p", "validate", "align"))
    for command in commands:
        _stdout, _stderr, returncode, error = _run(command, timeout=timeout)
        if error == "executable_missing":
            return _check("mfa_help", False, "executable_missing", "MFA command help could not be started", "Activate the MFA environment and verify MFA subcommands.", command)
        if error == "timeout":
            return _check("mfa_help", False, "command_timeout", "MFA help probe timed out", "Retry after checking the MFA environment.", command)
        if returncode != 0:
            return _check("mfa_help", False, "command_failed", "MFA required subcommand is unavailable", "Run g2p, validate, and align with `--help` in the MFA environment.", command)
    return _check("mfa_help", True, "ok", "MFA g2p/validate/align commands are available", command=commands[0])


def _mfa_model(config: PipelineConfig, kind: str, timeout: float) -> PreflightCheck:
    model = config.mfa.acoustic_model if kind == "acoustic" else config.mfa.g2p_model
    command = (*config.commands.mfa, "model", "inspect", kind, model)
    _stdout, _stderr, returncode, error = _run(command, timeout=timeout)
    name = f"mfa_{kind}_model"
    if error == "executable_missing":
        return _check(name, False, "executable_missing", "MFA model registry could not be queried", "Activate the MFA environment and run `mfa model inspect`.", command)
    if error == "timeout":
        return _check(name, False, "command_timeout", "MFA model probe timed out", "Retry after checking the local MFA model registry.", command)
    if returncode != 0:
        return _check(name, False, "model_unavailable", f"configured Japanese MFA {kind} model is unavailable", f"Install or register the configured {kind} model before running alignment.", command)
    return _check(name, True, "ok", f"configured Japanese MFA {kind} model is available", command=command)


def _asr_executable(config: PipelineConfig) -> str:
    return config.commands.asr_worker[0]


def _asr_runtime(config: PipelineConfig, timeout: float) -> PreflightCheck:
    executable = _asr_executable(config)
    command = (executable, "-c", "import qwen_asr; print(getattr(qwen_asr, '__version__', 'unknown'))")
    _stdout, _stderr, returncode, error = _run(command, timeout=timeout)
    if error == "executable_missing":
        return _check("qwen_runtime", False, "executable_missing", "Qwen ASR interpreter could not be started", "Activate the isolated ASR environment and verify `import qwen_asr`.", command)
    if error == "timeout":
        return _check("qwen_runtime", False, "command_timeout", "Qwen ASR runtime probe timed out", "Retry after checking the ASR environment.", command)
    if returncode != 0:
        return _check("qwen_runtime", False, "runtime_unavailable", "qwen_asr cannot be imported by the configured ASR interpreter", "Install qwen-asr in the isolated Python 3.12 ASR environment.", command)
    return _check("qwen_runtime", True, "ok", "qwen_asr runtime is importable", command=command)


def _asr_model(config: PipelineConfig) -> PreflightCheck:
    configured = os.environ.get("JAPANMFA_ASR_MODEL_PATH")
    if configured:
        path = Path(configured).expanduser()
        if path.is_dir():
            return _check("qwen_model", True, "ok", "configured Qwen model directory is present")
        return _check("qwen_model", False, "model_unavailable", "configured Qwen model directory is absent", "Set JAPANMFA_ASR_MODEL_PATH to a local Qwen3-ASR model directory.")
    hf_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    cache_name = "models--" + config.asr.model.replace("/", "--")
    path = hf_home / "hub" / cache_name
    if path.is_dir():
        return _check("qwen_model", True, "ok", "Qwen model is present in the configured Hugging Face cache")
    return _check("qwen_model", False, "model_unavailable", "configured Qwen model was not found locally", "Download the configured Qwen3-ASR model into an isolated cache, then rerun check.")


def _qwen_cuda(config: PipelineConfig, timeout: float) -> PreflightCheck:
    if os.environ.get("JAPANMFA_REQUIRE_CUDA", "0").lower() not in {"1", "true", "yes"}:
        return _check("qwen_cuda", True, "not_required", "CUDA check not required; CPU policy is not explicitly disabled")
    executable = _asr_executable(config)
    command = (executable, "-c", "import torch; print(torch.cuda.is_available())")
    stdout, _stderr, returncode, error = _run(command, timeout=timeout)
    if error or returncode != 0:
        return _check("qwen_cuda", False, "cuda_probe_failed", "could not determine CUDA availability for Qwen", "Install a CUDA-enabled ASR runtime or unset JAPANMFA_REQUIRE_CUDA to allow CPU policy.", command)
    if stdout.strip().lower() not in {"1", "true", "yes"}:
        return _check("qwen_cuda", False, "cuda_unavailable", "CUDA is unavailable while CPU execution is explicitly disallowed", "Use a CUDA-enabled ASR environment or unset JAPANMFA_REQUIRE_CUDA to allow CPU policy.", command)
    return _check("qwen_cuda", True, "ok", "CUDA is available for Qwen", command=command)


def _writable(name: str, path: Path) -> PreflightCheck:
    path = path.expanduser()
    try:
        if path.exists() and (not path.is_dir() or path.is_symlink()):
            raise OSError("path is not a writable directory")
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=".japanmfa-check-", dir=path, delete=False) as handle:
            child = Path(handle.name)
            handle.write(b"check")
        child.unlink()
    except OSError:
        return _check(f"{name}_writable", False, "path_not_writable", f"{name} path cannot create a temporary child file", f"Choose a writable project-owned {name} directory.")
    return _check(f"{name}_writable", True, "ok", f"{name} path accepts a temporary child file")


def _canonical_katakana(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return "".join(chr(ord(char) + 0x60) if "ぁ" <= char <= "ゖ" else char for char in normalized)


def _tdmelodic_probe(timeout: float) -> PreflightCheck:
    raw = os.environ.get("JAPANMFA_TDMELODIC_COMMAND", "tdmelodic")
    try:
        command = tuple(shlex.split(raw))
    except ValueError:
        return _check("tdmelodic_probe", False, "probe_malformed", "tdmelodic command configuration is malformed", "Set JAPANMFA_TDMELODIC_COMMAND as an argv-like command.")
    if not command:
        return _check("tdmelodic_probe", False, "probe_malformed", "tdmelodic command configuration is empty", "Set JAPANMFA_TDMELODIC_COMMAND to the isolated tdmelodic command.")
    stdout, _stderr, returncode, error = _run(command, input_text=f"{_PROBE_SURFACE},{_PROBE_YOMI}\n", timeout=timeout)
    if error == "executable_missing":
        return _check("tdmelodic_probe", False, "executable_missing", "tdmelodic executable could not be started", "Build or activate the isolated tdmelodic runtime, then set JAPANMFA_TDMELODIC_COMMAND.", command)
    if error == "timeout":
        return _check("tdmelodic_probe", False, "command_timeout", "tdmelodic probe timed out", "Retry after checking the isolated tdmelodic runtime.", command)
    lines = stdout.splitlines()
    marked = lines[0].strip() if len(lines) == 1 else ""
    try:
        probe_token = Token(0, 0, len(_PROBE_YOMI), _PROBE_SURFACE, (), _PROBE_YOMI, "override")
        parse_accent(marked, segment_morae(probe_token))
    except Exception:
        marked = ""
    if returncode != 0 or len(lines) != 1 or not marked:
        return _check("tdmelodic_probe", False, "probe_malformed", "tdmelodic probe did not round-trip the supplied reading", "Verify `sy2a(surface, yomi)` output and the isolated tdmelodic command.", command)
    return _check("tdmelodic_probe", True, "ok", "tdmelodic probe round-tripped the supplied reading", command=command)


def run_preflight(config: PipelineConfig) -> PreflightReport:
    """Run bounded checks for all configured runtime and model dependencies."""

    timeout = _DEFAULT_TIMEOUT
    checks = (
        _mfa_version(config, timeout),
        _mfa_help(config, timeout),
        _mfa_model(config, "acoustic", timeout),
        _mfa_model(config, "g2p", timeout),
        _asr_runtime(config, timeout),
        _asr_model(config),
        _qwen_cuda(config, timeout),
        _tdmelodic_probe(timeout),
        _writable("output", config.paths.output_dir),
        _writable("cache", config.paths.cache_dir),
    )
    return PreflightReport(ok=all(check.ok for check in checks), checks=checks)


__all__ = ["PreflightCheck", "PreflightReport", "run_preflight"]
