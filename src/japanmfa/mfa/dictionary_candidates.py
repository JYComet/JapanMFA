"""Exact geminate pronunciations verified in the pinned MFA v3 dictionary.

The source dictionary SHA-256 is
4a0c66760576e4b7f3748f3169e7d5217c0135f857f0b5d34637c93a85fd1c91.
Only a G2P sequence differing by the one missing length mark can use a row.
"""

from __future__ import annotations


_GEMINATE_PRONUNCIATIONS: dict[str, tuple[str, ...]] = {
    # オッパイ / おっぱい
    "オッパイ": ("o", "pː", "a", "i"),
    # まったく, せっかく, かってに (canonical locked Katakana readings)
    "マッタク": ("m", "a", "tː", "a", "k", "ɯ"),
    "セッカク": ("s", "e", "kː", "a", "k", "ɯ"),
    "カッテニ": ("k", "a", "tː", "e", "ɲ", "i"),
}


def exact_missing_geminate_candidate(
    reading: str, g2p_candidates: tuple[tuple[str, ...], ...]
) -> tuple[str, ...] | None:
    """Return one dictionary candidate only for an omitted geminate mark."""
    verified = _GEMINATE_PRONUNCIATIONS.get(reading)
    if verified is None:
        return None
    geminates = [index for index, phone in enumerate(verified) if phone.endswith("ː")]
    if len(geminates) != 1:
        return None
    index = geminates[0]
    unlengthened = (*verified[:index], verified[index][:-1], *verified[index + 1:])
    return verified if unlengthened in g2p_candidates else None
