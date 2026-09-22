"""Deterministic mora segmentation for locked Katakana readings."""

from __future__ import annotations

from japanmfa.domain import Mora, Token


# These are the small characters that may form a single mora with the
# preceding kana.  Small tsu is deliberately excluded: it is a mora in its
# own right, as are the nasal and long-vowel marks below.
_COMBINING_SMALL_KANA = frozenset("ァィゥェォャュョヮヵヶ")
_STANDALONE_KANA = frozenset("ッンー")


def _is_katakana(character: str) -> bool:
    """Return whether *character* is a supported full-width Katakana kana."""
    return "ァ" <= character <= "ヺ"


def segment_morae(token: Token) -> tuple[Mora, ...]:
    """Split a locked token reading into uniquely identifiable morae.

    ``Token.reading`` is expected to be the canonical Katakana reading
    produced by the frontend.  The small set above is intentionally explicit
    so unsupported or ambiguous Unicode characters fail closed rather than
    being silently folded into a neighbouring mora.
    """
    # The frontend has already locked readings to canonical Katakana.  Do not
    # apply compatibility folding here: accepting a different source code
    # point would make the locked reading and its mora trace diverge.
    reading = token.reading
    if not reading:
        raise ValueError("reading must not be empty")

    morae: list[str] = []
    for character in reading:
        if character in _STANDALONE_KANA:
            morae.append(character)
            continue
        if character in _COMBINING_SMALL_KANA:
            if not morae:
                raise ValueError(
                    f"leading combining small kana is unsupported: {character}"
                )
            if morae[-1] in _STANDALONE_KANA:
                raise ValueError(
                    f"small kana cannot combine with standalone mora {morae[-1]}"
                )
            if morae[-1][-1] in _COMBINING_SMALL_KANA:
                raise ValueError(
                    f"multiple combining small kana are unsupported: {morae[-1]}"
                )
            morae[-1] += character
            continue
        if not _is_katakana(character) or character == "・":
            raise ValueError(f"unsupported reading code point: {character!r}")
        morae.append(character)

    return tuple(
        Mora(token.index, index, kana) for index, kana in enumerate(morae)
    )
