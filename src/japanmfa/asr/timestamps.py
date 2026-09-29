"""Japanese Qwen lexical timestamps and punctuation gap projection."""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any


_MARKUP = re.compile(r"<\|[^|<>]*\|>|<\s*/?\s*[A-Za-z][A-Za-z0-9_-]*\s*>")


def _punctuation(character: str) -> bool:
    return unicodedata.category(character).startswith("P") or character in "〜～"


def _lexical(character: str) -> bool:
    return unicodedata.category(character)[0] in "LNM"


def _match_char(character: str) -> str:
    """Compare fullwidth ASCII letters/digits without changing source text."""
    if 0xFF10 <= ord(character) <= 0xFF5A:
        folded = unicodedata.normalize("NFKC", character)
        if len(folded) == 1 and _lexical(folded):
            return folded
    return character


def clean_asr_text(text: str) -> str:
    """Remove Qwen markup and unspoken symbols while retaining punctuation."""
    if not isinstance(text, str):
        raise ValueError("ASR text must be a string")
    without_markup = _MARKUP.sub("", text)
    result = "".join(
        character for character in without_markup
        if _lexical(character) or _punctuation(character) or character.isspace()
    )
    return " ".join(result.split())


def _field(item: Any, *names: str) -> Any:
    for name in names:
        value = item.get(name) if isinstance(item, Mapping) else getattr(item, name, None)
        if value is not None:
            return value
    return None


def _items(raw: Any) -> Sequence[Any]:
    if isinstance(raw, (list, tuple)) and len(raw) == 1 and _field(raw[0], "items") is not None:
        raw = raw[0]
    nested = _field(raw, "items", "segments")
    if nested is not None:
        raw = nested() if callable(nested) else nested
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ValueError("forced aligner returned no lexical items")
    return raw


def project_timestamps(text: str, alignment: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Match model units to source text and assign punctuation to real gaps.

    Qwen does not align punctuation acoustically. A positive lexical gap owns
    the intervening punctuation; without a gap it gets a boundary point.
    """
    positions = [index for index, character in enumerate(text) if _lexical(character)]
    stream = "".join(_match_char(text[index]) for index in positions)
    if not stream:
        raise ValueError("Japanese alignment text has no lexical characters")
    lexical: list[dict[str, Any]] = []
    source_spans: list[tuple[int, int]] = []
    internal_punctuation: list[list[dict[str, Any]]] = []
    cursor = 0
    previous_end = 0.0
    for item in _items(alignment):
        unit = _field(item, "text", "unit", "word")
        if not isinstance(unit, str) or not unit:
            raise ValueError("forced aligner item has no text")
        item_stream = "".join(_match_char(character) for character in unit if _lexical(character))
        # Qwen can return punctuation as a separate zero-duration item. The
        # source text owns that mark; it has no lexical span to align.
        if not item_stream:
            continue
        next_cursor = cursor + len(item_stream)
        expected = stream[cursor:next_cursor]
        if expected != item_stream:
            raise ValueError(
                "forced aligner lexical mismatch with Japanese text "
                f"at character {cursor}: expected={expected[:40]!r} got={item_stream[:40]!r}"
            )
        start = _field(item, "start_time", "start_s", "start")
        end = _field(item, "end_time", "end_s", "end")
        if isinstance(start, bool) or isinstance(end, bool):
            raise ValueError("forced aligner timestamp is not numeric")
        try:
            start, end = float(start), float(end)
        except (TypeError, ValueError) as exc:
            raise ValueError("forced aligner timestamp is not numeric") from exc
        if not math.isfinite(start) or not math.isfinite(end) or start < previous_end or end < start:
            raise ValueError("forced aligner timestamps are invalid or overlap")
        # Zero-width lexical items occur with model timestamp quantization. The
        # evidence is retained as a point; MFA still supplies phone boundaries.
        source_start, source_end = positions[cursor], positions[next_cursor - 1] + 1
        surface = text[source_start:source_end]
        internal: list[dict[str, Any]] = []
        marks = ""
        for character in surface:
            if _punctuation(character):
                marks += character
            elif marks:
                internal.append({"text": marks, "start": start, "end": end, "source": "lexical_span"})
                marks = ""
        if marks:
            internal.append({"text": marks, "start": start, "end": end, "source": "lexical_span"})
        lexical.append({"text": surface, "start": start, "end": end})
        source_spans.append((source_start, source_end))
        internal_punctuation.append(internal)
        cursor = next_cursor
        previous_end = end
    if cursor != len(stream):
        raise ValueError(
            "forced aligner lexical mismatch with Japanese text "
            f"at character {cursor}: missing={stream[cursor:cursor + 40]!r}"
        )

    punctuation: list[dict[str, Any]] = []
    for boundary in range(len(lexical) + 1):
        left = source_spans[boundary - 1][1] if boundary else 0
        right = source_spans[boundary][0] if boundary < len(source_spans) else len(text)
        marks = "".join(character for character in text[left:right] if _punctuation(character))
        if not marks:
            if boundary < len(lexical):
                punctuation.extend(internal_punctuation[boundary])
            continue
        if boundary == 0:
            start = end = lexical[0]["start"]
        elif boundary == len(lexical):
            start = end = lexical[-1]["end"]
        else:
            start, end = lexical[boundary - 1]["end"], lexical[boundary]["start"]
        punctuation.append({
            "text": marks,
            "start": start,
            "end": end,
            "source": "lexical_gap" if end > start else "boundary_point",
        })
        if boundary < len(lexical):
            punctuation.extend(internal_punctuation[boundary])
    return lexical, punctuation
