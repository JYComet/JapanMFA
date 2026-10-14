"""A changed native recovery implementation can reuse validated old words."""

from japanmfa.mfa.word_cache import WordCache


def test_explicit_old_accent_identity_reuses_only_validated_accent_words(tmp_path, monkeypatch):
    cache = WordCache(tmp_path)
    pair = ("学校", "ガッコウ")
    cache.put("old", "accent", pair, "ガ[ッコウ")
    cache.put("old", "g2p", "ガッコウ", {"phones": ["g", "a"]})
    cache.commit()
    monkeypatch.setenv("JAPANMFA_ACCENT_COMPAT_IDENTITY", "old")

    assert cache.get("new", "accent", pair) == "ガ[ッコウ"
    assert cache.get("new", "g2p", "ガッコウ") is None
    monkeypatch.setenv("JAPANMFA_G2P_COMPAT_IDENTITY", "old")
    assert cache.get("new", "g2p", "ガッコウ") == {"phones": ["g", "a"]}
    cache.db.execute("UPDATE words SET sha='bad' WHERE identity='old' AND stage='accent'")
    cache.commit()
    assert cache.get("new", "accent", pair) is None
    cache.close()
