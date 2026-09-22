import json
from pathlib import Path

import pytest

from japanmfa.cache import StageCache, stage_fingerprint


def test_stage_fingerprint_is_canonical_and_changes_for_override(tmp_path: Path) -> None:
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"audio")
    first = stage_fingerprint(
        "frontend",
        {
            "audio_sha256": audio,
            "text_sha256": "text-sha",
            "config": {"split": "B", "reading_override": "old"},
            "model": "sudachi",
            "adapter_version": "1",
        },
    )
    same = stage_fingerprint(
        "frontend",
        {
            "adapter_version": "1",
            "model": "sudachi",
            "config": {"reading_override": "old", "split": "B"},
            "text_sha256": "text-sha",
            "audio_sha256": audio,
        },
    )
    changed = stage_fingerprint(
        "frontend",
        {
            "audio_sha256": audio,
            "text_sha256": "text-sha",
            "config": {"split": "B", "reading_override": "new"},
            "model": "sudachi",
            "adapter_version": "1",
        },
    )
    assert first == same
    assert first != changed
    assert len(first) == 64


def test_stage_cache_reuses_complete_stage_and_writes_matching_markers(tmp_path: Path) -> None:
    cache = StageCache(tmp_path / "cache")
    calls = 0

    def produce(path: Path) -> dict[str, object]:
        nonlocal calls
        calls += 1
        (path / "diagnostic.txt").write_text("ok", encoding="utf-8")
        return {"value": 7}

    first = cache.load_or_run("audio", "a" * 64, produce)
    second = cache.load_or_run("audio", "a" * 64, produce)
    assert first == second == {"value": 7}
    assert calls == 1
    stage = tmp_path / "cache" / "audio" / ("a" * 64)
    assert json.loads((stage / "complete.json").read_text()) == {"fingerprint": "a" * 64}
    assert json.loads((stage / "result.json").read_text()) == {"value": 7}


def test_stage_cache_does_not_publish_after_producer_exception(tmp_path: Path) -> None:
    cache = StageCache(tmp_path / "cache")

    def produce(_path: Path) -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        cache.load_or_run("mfa", "b" * 64, produce)

    stage_parent = tmp_path / "cache" / "mfa"
    assert not (stage_parent / ("b" * 64)).exists()
    assert not list(stage_parent.glob("b" * 64 + "/complete.json"))


def test_stage_cache_ignores_stale_partial_directory(tmp_path: Path) -> None:
    cache = StageCache(tmp_path / "cache")
    stale = tmp_path / "cache" / "frontend" / ("c" * 64)
    stale.mkdir(parents=True)
    (stale / "result.json").write_text('{"stale": true}', encoding="utf-8")

    result = cache.load_or_run("frontend", "c" * 64, lambda _path: {"fresh": True})
    assert result == {"fresh": True}
    assert json.loads((stale / "complete.json").read_text()) == {"fingerprint": "c" * 64}


def test_stage_cache_cleans_its_temporary_tree_after_producer_exception(tmp_path: Path) -> None:
    cache = StageCache(tmp_path / "cache")
    fingerprint = "d" * 64

    def produce(path: Path) -> None:
        (path / "nested").mkdir()
        (path / "nested" / "partial.bin").write_bytes(b"partial")
        raise RuntimeError("producer failed")

    with pytest.raises(RuntimeError, match="producer failed"):
        cache.load_or_run("audio", fingerprint, produce)
    assert not list((tmp_path / "cache" / "audio").glob(f".{fingerprint}.*"))


def test_stage_cache_validates_required_sidecar_on_cache_hit(tmp_path: Path) -> None:
    cache = StageCache(tmp_path / "cache")
    fingerprint = "e" * 64
    calls = 0

    def produce(path: Path) -> dict[str, bool]:
        nonlocal calls
        calls += 1
        (path / "audio.wav").write_bytes(b"non-empty")
        return {"ok": True}

    valid = lambda path: (path / "audio.wav").is_file() and (path / "audio.wav").stat().st_size > 0
    cache.load_or_run("audio", fingerprint, produce, validate=valid)
    (cache.directory("audio", fingerprint) / "audio.wav").write_bytes(b"")
    cache.load_or_run("audio", fingerprint, produce, validate=valid)
    assert calls == 2


class _StableAdapter:
    def __init__(self) -> None:
        self.model = "model"
        self.version = "1"
        self.runtime_object = object()


def test_adapter_identity_does_not_include_object_repr_or_address() -> None:
    from japanmfa.pipeline import _adapter_id

    assert _adapter_id(_StableAdapter()) == _adapter_id(_StableAdapter())
