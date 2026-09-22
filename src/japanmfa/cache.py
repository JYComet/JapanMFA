"""Content-addressed, atomically published stage cache."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import stat
import shutil
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
        if any(not isinstance(key, str) for key in value):
            raise TypeError("string mapping keys are required for fingerprints")
        return {str(key): _canonical(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, (set, frozenset)):
        entries = [_canonical(item) for item in value]
        entries.sort(key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
        return {"__type__": "set" if isinstance(value, set) else "frozenset", "items": entries}
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
        configured = Path(root)
        if ".." in configured.parts:
            raise ValueError("cache root must not contain parent traversal")
        self.root = configured.absolute()
        self._assert_no_symlink_ancestors(self.root)

    @staticmethod
    def _assert_no_symlink_ancestors(path: Path) -> None:
        current = Path(path).absolute()
        while True:
            if current.is_symlink():
                raise ValueError(f"cache path component is a symlink: {current}")
            if current.parent == current:
                return
            current = current.parent

    def _stage_dir(self, stage: str, fingerprint: str) -> Path:
        if not stage or Path(stage).name != stage or stage in {".", ".."}:
            raise ValueError("stage must be a single path component")
        if not fingerprint or Path(fingerprint).name != fingerprint or fingerprint in {".", ".."}:
            raise ValueError("fingerprint must be a single path component")
        current = self.root
        for component in (stage, fingerprint):
            if current.exists() and current.is_symlink():
                raise ValueError(f"cache path component is a symlink: {current}")
            current = current / component
        if current.exists() and current.is_symlink():
            raise ValueError(f"cache path component is a symlink: {current}")
        self._assert_no_symlink_ancestors(current)
        return current

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

    def load_or_run(
        self,
        stage: str,
        fingerprint: str,
        producer: Callable[[Path], T],
        *,
        validate: Callable[[Path], bool] | None = None,
        required_files: Sequence[str] = (),
    ) -> T:
        """Return a complete cached value, or run and atomically publish *producer*."""
        final = self._stage_dir(stage, fingerprint)
        cached = self._load_complete(final, fingerprint) if final.is_dir() else _MISSING
        if cached is not _MISSING and not self._artifacts_valid(final, required_files, validate):
            cached = _MISSING
        if cached is not _MISSING:
            return cached  # type: ignore[return-value]

        parent = final.parent
        parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=f".{fingerprint}.", dir=parent))
        try:
            value = producer(temporary)
            if not self._artifacts_valid(temporary, required_files, validate):
                raise ValueError(f"artifact validation failed for stage {stage}")
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
                # The path is a resolved child created by this method. Cleanup
                # must never replace the producer's original exception.
                try:
                    shutil.rmtree(temporary)
                except Exception:
                    pass

    @staticmethod
    def _artifacts_valid(
        directory: Path,
        required_files: Sequence[str],
        validate: Callable[[Path], bool] | None,
    ) -> bool:
        try:
            for name in required_files:
                if not isinstance(name, str):
                    return False
                relative = Path(name)
                if not name or relative.is_absolute() or ".." in relative.parts:
                    return False
                path = directory
                parts = relative.parts
                if not parts or parts == (".",):
                    return False
                for component in parts:
                    path = path / component
                    if path.is_symlink():
                        return False
                metadata = path.stat()
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_size <= 0:
                    return False
            return validate is None or bool(validate(directory))
        except (OSError, ValueError):
            return False


__all__ = ["StageCache", "stage_fingerprint"]
