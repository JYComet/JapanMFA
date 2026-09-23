"""Atomic JSON and locked JSONL reporting for pipeline outcomes."""

from __future__ import annotations

import json
import math
import os
import platform
import re
import tempfile
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from japanmfa import __version__
from japanmfa.domain import UtteranceOutcome


try:
    import fcntl
except ImportError:  # pragma: no cover - this project runs on POSIX
    fcntl = None  # type: ignore[assignment]


_RUN_ID = os.environ.get("JAPANMFA_RUN_ID") or uuid.uuid4().hex
_SENSITIVE_MARKERS = frozenset(
    {
        "apikey",
        "accesskey",
        "accesstoken",
        "authorization",
        "credential",
        "hfkey",
        "hftoken",
        "password",
        "privatekey",
        "secret",
        "token",
        "auth",
    }
)
_STATUSES = ("aligned", "skipped", "failed")


def _sensitive_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
    for marker in _SENSITIVE_MARKERS:
        # ``authoritative`` is an audit term, not an authentication secret;
        # avoid treating it as the ``auth`` marker.
        if marker == "auth" and normalized.startswith("authoritative"):
            continue
        if marker in normalized:
            return True
    return False


def _secret_values() -> frozenset[str]:
    return frozenset(
        value
        for key, value in os.environ.items()
        if _sensitive_key(key) and value
    )


def _redact_string(value: str) -> str:
    for secret in sorted(_secret_values(), key=len, reverse=True):
        value = value.replace(secret, "[REDACTED]")
    return value


def redact_command(command: Sequence[str]) -> list[str]:
    """Redact values attached to secret-like command-line options."""
    rendered: list[str] = []
    redact_next = False
    for raw in command:
        argument = str(raw)
        if redact_next:
            rendered.append("<redacted>")
            redact_next = False
            continue
        if argument.startswith("-"):
            option, separator, _value = argument.partition("=")
            if _sensitive_key(option.lstrip("-")):
                if separator:
                    rendered.append(f"{option}=<redacted>")
                else:
                    rendered.append(option)
                    redact_next = True
                continue
        rendered.append(_redact_string(argument))
    return rendered


def _safe(value: Any, *, key: str | None = None) -> Any:
    if key and _sensitive_key(key):
        return "[REDACTED]"
    if isinstance(value, Path):
        return _redact_string(str(value))
    if isinstance(value, Mapping):
        return {str(name): _safe(item, key=str(name)) for name, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    if isinstance(value, set | frozenset):
        return [_safe(item) for item in sorted(value, key=str)]
    if isinstance(value, str):
        return _redact_string(value)
    return value


def _safe_payload(payload: Mapping[str, object]) -> Any:
    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a mapping")
    return _safe(payload)


def _json_bytes(payload: Mapping[str, object]) -> bytes:
    try:
        rendered = json.dumps(
            _safe_payload(payload), ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("payload is not JSON serializable") from exc
    return (rendered + "\n").encode("utf-8")


def _yaml_bytes(payload: Mapping[str, object]) -> bytes:
    try:
        rendered = yaml.safe_dump(
            _safe_payload(payload),
            allow_unicode=True,
            sort_keys=True,
            default_flow_style=False,
        )
    except (TypeError, ValueError, yaml.YAMLError) as exc:
        raise ValueError("payload is not YAML serializable") from exc
    return rendered.encode("utf-8")


def _atomic_write(path: Path, data: bytes) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def write_json(path: Path, payload: Mapping[str, object]) -> None:
    """Atomically write stable UTF-8 JSON with no environment secrets."""
    _atomic_write(Path(path), _json_bytes(payload))


def write_yaml(path: Path, payload: Mapping[str, object]) -> None:
    """Atomically write stable UTF-8 YAML with no environment secrets."""
    _atomic_write(Path(path), _yaml_bytes(payload))


def _validate_outcome(outcome: UtteranceOutcome) -> None:
    if not isinstance(outcome, UtteranceOutcome):
        raise TypeError("outcome must be an UtteranceOutcome")
    if not isinstance(outcome.utterance_id, str) or not outcome.utterance_id:
        raise ValueError("utterance_id must be a non-empty string")
    if outcome.status not in _STATUSES:
        raise ValueError("status must be aligned, skipped, or failed")
    if outcome.status == "aligned" and outcome.reason_code is not None:
        raise ValueError("aligned outcome reason_code must be None")
    if outcome.status in {"skipped", "failed"} and (
        not isinstance(outcome.reason_code, str) or not outcome.reason_code
    ):
        raise ValueError("skipped and failed outcomes require a reason_code")
    if outcome.message is not None and not isinstance(outcome.message, str):
        raise ValueError("message must be a string or None")
    if outcome.artifact_dir is not None and not isinstance(outcome.artifact_dir, Path):
        raise ValueError("artifact_dir must be a Path or None")
    if not isinstance(outcome.stage_durations, Mapping):
        raise ValueError("stage_durations must be a mapping")
    for stage, seconds in outcome.stage_durations.items():
        if not isinstance(stage, str) or not stage:
            raise ValueError("stage duration names must be non-empty strings")
        if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or not math.isfinite(seconds) or seconds < 0:
            raise ValueError("stage durations must be finite non-negative numbers")


def _relative_artifact(manifest: Path, artifact: Path | None) -> str | None:
    if artifact is None:
        return None
    if not artifact.is_absolute():
        return str(artifact)
    return os.path.relpath(str(artifact), start=str(manifest.parent.resolve()))


def append_manifest(path: Path, outcome: UtteranceOutcome, *, source_type: str = "unknown") -> None:
    """Append one validated, traceable outcome while holding an inter-process lock."""
    _validate_outcome(outcome)
    if source_type not in {"txt", "asr", "unknown"}:
        raise ValueError("source_type must be txt, asr, or unknown")
    manifest = Path(path)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    record: dict[str, object] = {
        "artifact_dir": _relative_artifact(manifest, outcome.artifact_dir),
        "message": outcome.message,
        "reason_code": outcome.reason_code,
        "run_id": os.environ.get("JAPANMFA_RUN_ID") or _RUN_ID,
        "source_type": source_type,
        "stage": "pipeline",
        "stage_durations": dict(sorted(outcome.stage_durations.items())),
        "status": outcome.status,
        "tool_versions": {"japanmfa": __version__, "python": platform.python_version()},
        "trace_ids": {"utterance_id": outcome.utterance_id},
        "utterance_id": outcome.utterance_id,
    }
    line = json.dumps(_safe(record), ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n"
    with manifest.open("a+b") as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() > 0:
                handle.seek(-1, os.SEEK_END)
                if handle.read(1) != b"\n":
                    handle.seek(0, os.SEEK_END)
                    handle.write(b"\n")
            handle.seek(0, os.SEEK_END)
            handle.write(line.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def summarize(outcomes: Sequence[UtteranceOutcome]) -> dict[str, object]:
    """Return deterministic aligned/skipped/failed counts and reason groups."""
    counts = {status: 0 for status in _STATUSES}
    reasons: dict[str, dict[str, int]] = {}
    for outcome in outcomes:
        _validate_outcome(outcome)
        counts[outcome.status] += 1
        if outcome.reason_code is not None:
            grouped = reasons.setdefault(outcome.status, {})
            grouped[outcome.reason_code] = grouped.get(outcome.reason_code, 0) + 1
    stable_reasons = {
        status: {reason: reasons[status][reason] for reason in sorted(reasons[status])}
        for status in sorted(reasons)
    }
    return {"total": sum(counts.values()), "counts": counts, "reasons": stable_reasons}


__all__ = [
    "append_manifest",
    "redact_command",
    "summarize",
    "write_json",
    "write_yaml",
]
