"""Sudachi-backed Japanese support validation and locked readings."""

from __future__ import annotations

import importlib
import re
import unicodedata
from typing import Any

from japanmfa.domain import SourceText, Token
from japanmfa.errors import SkipUtterance, StageFailure


_KATAKANA_RE = re.compile(r"[ァ-ヿー]+")
_ASCII_LATIN_RE = re.compile(r"[A-Za-z]")


def normalize_katakana(value: str) -> str:
    """Normalize hiragana readings to the canonical katakana form."""
    normalized = unicodedata.normalize("NFKC", value)
    return "".join(
        chr(ord(character) + 0x60)
        if "ぁ" <= character <= "ゖ"
        else character
        for character in normalized
    )


def _is_punctuation(surface: str) -> bool:
    """Return whether every character is Unicode punctuation."""
    return bool(surface) and all(
        unicodedata.category(character).startswith("P") for character in surface
    )


def _span_failure(message: str, **details: object) -> StageFailure:
    return StageFailure(
        "frontend", "token_span_mismatch", f"token_span_mismatch: {message}", details
    )


def _skip(message: str, **details: object) -> SkipUtterance:
    return SkipUtterance(
        "unsupported_japanese_text", f"unsupported_japanese_text: {message}", details
    )


class JapaneseFrontend:
    """Tokenize supported Japanese text and lock every reading to katakana.

    ``sudachi_module`` is an injectable module-shaped object used by tests. In
    production it is imported lazily so callers can report a typed setup
    failure without making the package import itself depend on SudachiPy.
    """

    def __init__(self, *, sudachi_module: Any | None = None) -> None:
        module = sudachi_module
        if module is None:
            try:
                module = importlib.import_module("sudachipy")
            except (ImportError, ModuleNotFoundError) as exc:
                raise StageFailure(
                    "frontend",
                    "sudachi_unavailable",
                    "SudachiPy is required for Japanese frontend tokenization; "
                    "install sudachipy and sudachidict-core",
                    {"error": str(exc)},
                ) from exc

        try:
            dictionary = module.Dictionary(dict="core")
            self._tokenizer = dictionary.create(mode=module.SplitMode.B)
        except Exception as exc:
            raise StageFailure(
                "frontend",
                "sudachi_dictionary_unavailable",
                "Sudachi core dictionary could not be created; install sudachidict-core",
                {"error": str(exc)},
            ) from exc

    def analyze(self, text: SourceText) -> tuple[Token, ...]:
        """Validate and tokenize one source text into pronounced tokens."""
        processing = text.processing
        if _ASCII_LATIN_RE.search(processing):
            raise _skip(
                "ASCII Latin letters are outside the supported Japanese frontend scope",
                text=processing,
            )
        if not processing:
            raise _skip("empty text is outside the supported Japanese frontend scope")

        try:
            morphemes = tuple(self._tokenizer.tokenize(processing))
        except Exception as exc:
            raise StageFailure(
                "frontend",
                "tokenization_failed",
                "Sudachi tokenization failed",
                {"error": str(exc)},
            ) from exc

        tokens: list[Token] = []
        cursor = 0
        for morpheme in morphemes:
            try:
                surface = str(morpheme.surface())
                start = int(morpheme.begin())
                end = start + len(surface)
            except (AttributeError, TypeError, ValueError) as exc:
                raise _span_failure(
                    "Sudachi returned a malformed morpheme", error=str(exc)
                ) from exc

            if start != cursor or start < 0 or end < start or end > len(processing):
                raise _span_failure(
                    "Sudachi morpheme spans cannot be reconciled to SourceText.processing",
                    expected_start=cursor,
                    start=start,
                    end=end,
                )
            if processing[start:end] != surface:
                raise _span_failure(
                    "Sudachi morpheme surface does not match SourceText.processing",
                    surface=surface,
                    source_surface=processing[start:end],
                    start=start,
                    end=end,
                )
            cursor = end

            try:
                part_of_speech = tuple(str(item) for item in morpheme.part_of_speech())
                raw_reading = morpheme.reading_form()
            except (AttributeError, TypeError, ValueError) as exc:
                raise StageFailure(
                    "frontend",
                    "malformed_morpheme",
                    "Sudachi returned a morpheme without reading or part-of-speech data",
                    {"surface": surface, "error": str(exc)},
                ) from exc

            if _is_punctuation(surface) and not _KATAKANA_RE.fullmatch(surface):
                continue
            if not isinstance(raw_reading, str) or not raw_reading:
                raise _skip(
                    "text contains an unpronounceable morpheme",
                    surface=surface,
                    start=start,
                    end=end,
                )
            reading = normalize_katakana(raw_reading)
            if not _KATAKANA_RE.fullmatch(reading):
                raise _skip(
                    "text contains a morpheme without a stable katakana reading",
                    surface=surface,
                    reading=raw_reading,
                    start=start,
                    end=end,
                )
            tokens.append(
                Token(
                    index=len(tokens),
                    start=start,
                    end=end,
                    surface=surface,
                    part_of_speech=part_of_speech,
                    reading=reading,
                    reading_source="sudachi",
                )
            )

        if cursor != len(processing):
            raise _span_failure(
                "Sudachi morphemes do not cover SourceText.processing",
                cursor=cursor,
                source_length=len(processing),
            )
        if not tokens:
            raise _skip("text contains no pronounced Japanese morphemes", text=processing)
        return tuple(tokens)


def render_locked_kana(original: str, tokens: tuple[Token, ...]) -> str:
    """Replace pronounced token spans with locked readings and preserve gaps."""
    pieces: list[str] = []
    cursor = 0
    for token in tokens:
        if token.start < cursor:
            raise _span_failure(
                "token spans overlap or decrease",
                token_index=token.index,
                start=token.start,
                previous_end=cursor,
            )
        if token.start < 0 or token.end <= token.start or token.end > len(original):
            raise _span_failure(
                "token span is outside the source text",
                token_index=token.index,
                start=token.start,
                end=token.end,
                source_length=len(original),
            )
        if original[token.start : token.end] != token.surface:
            raise _span_failure(
                "token surface does not match the stated source span",
                token_index=token.index,
                surface=token.surface,
                source_surface=original[token.start : token.end],
            )
        pieces.append(original[cursor : token.start])
        pieces.append(token.reading)
        cursor = token.end
    pieces.append(original[cursor:])
    return "".join(pieces)
