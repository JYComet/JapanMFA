"""Content-addressed, atomically published stage cache."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import tempfile
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Callable, TypeVar


T = TypeVar("T")
_MISSING = object()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical(value: Any) -> Any:
    """Convert supported values to a deterministic JSON-compatible value."""
    if isinstance(value, Path):
        if value.is_file():
            return {"sha256": _sha256(value)}
        return {"path": str(value)}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _canonical(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_canonical(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False))
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def stage_fingerprint(stage: str, inputs: Mapping[str, object]) -> str:
    """Hash a canonical stage identity and its content/config/model inputs."""
    if not isinstance(stage, str) or not stage:
        raise ValueError("stage must be a non-empty string")
    if not isinstance(inputs, Mapping):
        raise TypeError("inputs must be a mapping")
    payload = {"stage": stage, "inputs": _canonical(inputs)}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _jsonable(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [_jsonable(item) for item in sorted(value, key=str)]
    json.dumps(value, allow_nan=False)
    return value


class StageCache:
    """Cache stage results in ``root/stage/fingerprint`` directories.

    Producers run in a temporary child of the stage parent.  A complete marker
    is written before the temporary directory is atomically renamed, so a
    process interruption cannot make a partial stage look reusable.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _stage_dir(self, stage: str, fingerprint: str) -> Path:
        if not stage or Path(stage).name != stage or stage in {".", ".."}:
            raise ValueError("stage must be a single path component")
        if not fingerprint or Path(fingerprint).name != fingerprint or fingerprint in {".", ".."}:
            raise ValueError("fingerprint must be a single path component")
        return self.root / stage / fingerprint

    def directory(self, stage: str, fingerprint: str) -> Path:
        """Return the deterministic published directory for a stage identity."""
        return self._stage_dir(stage, fingerprint)

    @staticmethod
    def _load_complete(directory: Path, fingerprint: str) -> Any:
        marker = directory / "complete.json"
        result = directory / "result.json"
        try:
            metadata = json.loads(marker.read_text(encoding="utf-8"))
            if metadata != {"fingerprint": fingerprint}:
                return _MISSING
            return json.loads(result.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError):
            return _MISSING

    def load_or_run(self, stage: str, fingerprint: str, producer: Callable[[Path], T]) -> T:
        """Return a complete cached value, or run and atomically publish *producer*."""
        final = self._stage_dir(stage, fingerprint)
        cached = self._load_complete(final, fingerprint) if final.is_dir() else _MISSING
        if cached is not _MISSING:
            return cached  # type: ignore[return-value]

        parent = final.parent
        parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=f".{fingerprint}.", dir=parent))
        try:
            value = producer(temporary)
            result = _jsonable(value)
            (temporary / "result.json").write_text(
                json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
                encoding="utf-8",
            )
            (temporary / "complete.json").write_text(
                json.dumps({"fingerprint": fingerprint}, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            if final.exists():
                stale = parent / f".{fingerprint}.stale-{uuid.uuid4().hex}"
                os.replace(final, stale)
            os.replace(temporary, final)
            temporary = Path()
            return value
        finally:
            if str(temporary) not in {"", "."} and temporary.exists():
                # The path is a resolved child created by this method.
                for child in temporary.iterdir():
                    if child.is_file() or child.is_symlink():
                        child.unlink(missing_ok=True)
                temporary.rmdir()


__all__ = ["StageCache", "stage_fingerprint"]
