"""Sudachi-backed Japanese support validation and locked readings."""

from __future__ import annotations

import importlib
import re
import unicodedata
from dataclasses import replace
from typing import Any

from japanmfa.domain import SourceText, Token
from japanmfa.errors import SkipUtterance, StageFailure


_KATAKANA_RE = re.compile(r"[ァ-ヿー]+")
_ASCII_LATIN_RE = re.compile(r"[A-Za-z]")
_YOON_STEMS = frozenset("キシチニヒミリギジヂビピ")
_FOREIGN_YU_STEMS = frozenset("デフ")
_SMALL_YOON = frozenset("ゃゅょャュョ")


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
        (unicodedata.category(character).startswith("P") or character in "～〜") for character in surface
    )


def _is_symbol(surface: str) -> bool:
    """Return whether any character is a Unicode symbol."""
    return any(unicodedata.category(character).startswith("S") for character in surface)


def _processing_projection(original: str) -> tuple[str, tuple[tuple[int, int], ...]]:
    """Return NFC processing text and source spans for every output character.

    NFC can compose multiple source code points into one output code point.
    Build normalization clusters first so each output character retains the
    complete original ``[start, end)`` span of the cluster that produced it.
    """
    source_units = [
        (index, character)
        for index, character in enumerate(original)
        if character not in "\r\n"
    ]
    clusters: list[list[tuple[int, str]]] = []
    for unit in source_units:
        if clusters and unicodedata.combining(unit[1]) != 0:
            clusters[-1].append(unit)
        else:
            clusters.append([unit])

    characters: list[str] = []
    source_spans: list[tuple[int, int]] = []
    for cluster in clusters:
        normalized = unicodedata.normalize("NFC", "".join(item[1] for item in cluster))
        source_span = (cluster[0][0], cluster[-1][0] + 1)
        characters.extend(normalized)
        source_spans.extend([source_span] * len(normalized))

    joined = "".join(characters)
    left_trimmed = len(joined) - len(joined.lstrip())
    right_trimmed = len(joined.rstrip())
    return (
        joined[left_trimmed:right_trimmed],
        tuple(source_spans[left_trimmed:right_trimmed]),
    )


def _span_failure(message: str, **details: object) -> StageFailure:
    return StageFailure(
        "frontend", "token_span_mismatch", f"token_span_mismatch: {message}", details
    )


def _skip(message: str, **details: object) -> SkipUtterance:
    return SkipUtterance(
        "unsupported_japanese_text", f"unsupported_japanese_text: {message}", details
    )


def _join_split_yoon(tokens: list[Token]) -> tuple[Token, ...]:
    """Rejoin kana that Sudachi split inside one pronounced yoon syllable."""
    joined: list[Token] = []
    joined_yoon = False
    for token in tokens:
        previous = joined[-1] if joined else None
        adjacent = previous is not None and previous.end == token.start
        is_yoon = (adjacent and token.surface in _SMALL_YOON
                   and token.reading == normalize_katakana(token.surface)
                   and (previous.reading[-1] in _YOON_STEMS
                        or token.reading == "ュ" and previous.reading[-1] in _FOREIGN_YU_STEMS)
                   and ("ぁ" <= previous.surface[-1] <= "ゖ"
                        or "ァ" <= previous.surface[-1] <= "ヿ"))
        is_long_mark = adjacent and joined_yoon and token.surface == token.reading == "ー"
        if is_yoon or is_long_mark:
            joined[-1] = replace(previous, end=token.end,
                                 surface=previous.surface + token.surface,
                                 reading=previous.reading + token.reading)
            joined_yoon = True
        else:
            joined.append(token)
            joined_yoon = False
    return tuple(replace(token, index=index) for index, token in enumerate(joined))


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
        processing = unicodedata.normalize("NFC", text.processing)
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

            if start != cursor or start < 0 or end <= start or end > len(processing):
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

            if surface.isspace() or _is_punctuation(surface):
                continue
            if _is_symbol(surface):
                raise _skip(
                    "text contains an unsupported Unicode symbol",
                    surface=surface,
                    start=start,
                    end=end,
                )
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
        return _join_split_yoon(tokens)


def render_locked_kana(original: str, tokens: tuple[Token, ...]) -> str:
    """Replace pronounced token spans with locked readings and preserve gaps."""
    mapped_tokens = _map_token_spans(original, tokens)
    pieces: list[str] = []
    cursor = 0
    for token, (start, end) in mapped_tokens:
        pieces.append(original[cursor:start])
        pieces.append(token.reading)
        cursor = end
    pieces.append(original[cursor:])
    return "".join(pieces)


def _map_token_spans(
    original: str, tokens: tuple[Token, ...]
) -> tuple[tuple[Token, tuple[int, int]], ...]:
    """Map processing-copy token spans to original-text character spans."""
    processing, source_spans = _processing_projection(original)
    mapped: list[tuple[Token, tuple[int, int]]] = []
    previous_end = 0
    for token in tokens:
        if token.start < previous_end:
            raise _span_failure(
                "token spans overlap or decrease",
                token_index=token.index,
                start=token.start,
                previous_end=previous_end,
            )
        if token.start < 0 or token.end <= token.start or token.end > len(processing):
            raise _span_failure(
                "token span is outside the processing text",
                token_index=token.index,
                start=token.start,
                end=token.end,
                processing_length=len(processing),
            )
        source_surface = processing[token.start : token.end]
        if source_surface != token.surface:
            raise _span_failure(
                "token surface does not match the processing text",
                token_index=token.index,
                surface=token.surface,
                processing_surface=source_surface,
                start=token.start,
                end=token.end,
            )
        try:
            original_start = source_spans[token.start][0]
            original_end = source_spans[token.end - 1][1]
        except IndexError as exc:
            raise _span_failure(
                "processing token span cannot be mapped to original text",
                token_index=token.index,
                start=token.start,
                end=token.end,
            ) from exc
        original_surface = original[original_start:original_end]
        original_surface = original_surface.replace("\r", "").replace("\n", "")
        if unicodedata.normalize("NFC", original_surface) != token.surface:
            raise _span_failure(
                "original text cannot reproduce the processing token",
                token_index=token.index,
                start=original_start,
                end=original_end,
            )
        mapped.append((token, (original_start, original_end)))
        previous_end = token.end
    return tuple(mapped)
