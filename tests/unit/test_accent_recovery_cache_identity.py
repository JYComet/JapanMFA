"""Changing the mounted recovery policy invalidates accent word results."""

import json

from japanmfa.cache import StageCache
from japanmfa.mfa import bulk_preparation


def test_accent_identity_tracks_native_recovery_code(tmp_path, monkeypatch):
    recovery = tmp_path / "recovery.py"
    recovery.write_text("policy = 1\n")
    monkeypatch.setattr(bulk_preparation, "ACCENT_RECOVERY_SOURCE", recovery)
    cache = StageCache(tmp_path / "cache")

    bulk_preparation.prime_preparation_cache([], cache, object(), object(), "model", tmp_path / "first")
    first = json.loads((tmp_path / "first/word-cache.json").read_text())
    recovery.write_text("policy = 2\n")
    bulk_preparation.prime_preparation_cache([], cache, object(), object(), "model", tmp_path / "second")
    second = json.loads((tmp_path / "second/word-cache.json").read_text())

    assert first["accent_identity"] != second["accent_identity"]
    assert first["g2p_identity"] == second["g2p_identity"]
