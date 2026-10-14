"""Conservative recovery for invalid single-word tdmelodic marker sequences.

This module has no runtime dependencies so the native accent container can use
the same decision code as the host tests.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

_SYMBOL = {0: "]", 1: "", 2: "["}


def _labels(marked: str, morae: Sequence[str]) -> tuple[int, ...] | None:
    offset = 0
    labels = []
    for mora in morae:
        if not marked.startswith(mora, offset):
            return None
        offset += len(mora)
        label = 1
        if offset < len(marked) and marked[offset] in "[]":
            label = 2 if marked[offset] == "[" else 0
            offset += 1
        labels.append(label)
    return tuple(labels) if offset == len(marked) else None


def _valid_transitions(labels: Sequence[int]) -> bool:
    first = next((label for label in labels if label != 1), None)
    high = first == 0
    for index, label in enumerate(labels):
        if label == 1:
            continue
        if index == len(labels) - 1:
            return label == 0
        if label == 2:
            if high:
                return False
            high = True
        elif label == 0:
            if not high:
                return False
            high = False
        else:
            return False
    return True


def _word_patterns(length: int):
    yield 0, (2,) + (1,) * (length - 1)
    yield 1, (0,) + (1,) * (length - 1)
    for accent in range(2, length + 1):
        yield accent, (2,) + (1,) * (accent - 2) + (0,) + (1,) * (length - accent)


def needs_recovery(marked: str, morae: Sequence[str]) -> bool:
    """Only transition conflicts with an intact reading may use a fallback."""
    labels = _labels(marked, morae)
    return len(morae) >= 2 and labels is not None and not _valid_transitions(labels)


def choose_repair(
    marked: str,
    surface: str,
    yomi: str,
    morae: Sequence[str],
    logits: Sequence[Sequence[float]],
    lexical_entries: Sequence[Mapping[str, str]],
) -> dict[str, object] | None:
    """Return a legal accent only when the exact lexicon and model agree.

    ``logits`` contains one row per mora in tdmelodic's ``]``, blank, ``[``
    class order. Valid original predictions are never changed.
    """
    length = len(morae)
    if length < 2 or "".join(morae) != yomi or len(logits) != length:
        return None
    labels = _labels(marked, morae)
    if labels is None or _valid_transitions(labels) or len(lexical_entries) != 1:
        return None
    entry = lexical_entries[0]
    accent_text = entry.get("acc", "")
    if (entry.get("surface") != surface or entry.get("kana") != yomi
            or not accent_text.isdecimal()):
        return None
    accent = int(accent_text)
    if not 0 <= accent <= length:
        return None
    try:
        scores = tuple(tuple(float(value) for value in row) for row in logits)
    except (TypeError, ValueError):
        return None
    if any(len(row) != 3 or not all(math.isfinite(value) for value in row) for row in scores):
        return None
    ranked = sorted(
        ((sum(scores[index][label] for index, label in enumerate(pattern)), kind, pattern)
         for kind, pattern in _word_patterns(length)),
        reverse=True,
    )
    if ranked[0][0] - ranked[1][0] <= 1e-6 or ranked[0][1] != accent:
        return None
    corrected = "".join(mora + _SYMBOL[label] for mora, label in zip(morae, ranked[0][2]))
    return {"raw": marked, "marked": corrected, "accent": accent,
            "evidence": "exact_unidic_and_constrained_model"}
