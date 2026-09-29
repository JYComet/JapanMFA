"""Attach full-sentence Japanese readings to Qwen lexical intervals."""

from __future__ import annotations

from collections.abc import Sequence

from japanmfa.asr.qwen3 import Timestamp
from japanmfa.asr.timestamps import _lexical, _punctuation
from japanmfa.domain import Token
from japanmfa.errors import StageFailure


def _mismatch(message: str) -> StageFailure:
    return StageFailure("asr", "reading_alignment_mismatch", message)


def merge_timed_words(
    text: str,
    lexical: Sequence[Timestamp],
    tokens: Sequence[Token],
) -> list[dict[str, str | float]]:
    """Merge crossed Qwen/Sudachi boundaries without splitting a reading.

    Sudachi reads the whole sentence first. If either tokenizer splits a unit
    differently, all overlapping units are joined into one timed output word.
    This keeps the original reading instead of guessing part of a kana string.
    """
    if not lexical or not tokens:
        raise _mismatch("lexical timestamps and Japanese readings are required")
    source_stream = "".join(character for character in text if _lexical(character))
    qwen_stream = "".join(character for item in lexical for character in item.text if _lexical(character))
    token_stream = "".join(character for token in tokens for character in token.surface if _lexical(character))
    if not source_stream or source_stream != qwen_stream or source_stream != token_stream:
        raise _mismatch("ASR lexical stream does not match Japanese reading tokens")

    spans: list[tuple[int, int]] = []
    cursor = 0
    for item in lexical:
        start = text.find(item.text, cursor)
        if start < 0 or any(_lexical(character) for character in text[cursor:start]):
            raise _mismatch("Qwen lexical item cannot be placed in ASR text")
        end = start + len(item.text)
        spans.append((start, end))
        cursor = end
    if any(_lexical(character) for character in text[cursor:]):
        raise _mismatch("Qwen lexical items do not cover ASR text")

    for token in tokens:
        if text[token.start:token.end] != token.surface:
            raise _mismatch("Japanese reading token has a mismatched source span")

    parent = list(range(len(tokens)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for item_start, item_end in spans:
        owners = [index for index, token in enumerate(tokens)
                  if token.start < item_end and item_start < token.end]
        if not owners:
            raise _mismatch("Qwen lexical item has no Japanese reading")
        for index in owners[1:]:
            parent[root(index)] = root(owners[0])

    groups: list[list[int]] = []
    for index in range(len(tokens)):
        if not groups or root(index) != root(groups[-1][0]):
            groups.append([index])
        else:
            groups[-1].append(index)

    result: list[dict[str, str | float]] = []
    covered_items: set[int] = set()
    for group in groups:
        first, last = tokens[group[0]], tokens[group[-1]]
        matches = [index for index, (start, end) in enumerate(spans)
                   if start < last.end and first.start < end]
        if not matches:
            raise _mismatch("Japanese reading has no Qwen timestamp")
        covered_items.update(matches)
        surface = text[first.start:last.end]
        if any(
            _punctuation(character) and not any(start <= offset < end for start, end in spans)
            for offset, character in enumerate(surface, start=first.start)
        ):
            raise _mismatch("one timed word would cross source punctuation")
        result.append({
            "text": surface,
            "kana": "".join(tokens[index].reading for index in group),
            "start": lexical[matches[0]].start,
            "end": lexical[matches[-1]].end,
        })
    if covered_items != set(range(len(lexical))):
        raise _mismatch("Qwen lexical item was not assigned to an output word")
    return result
