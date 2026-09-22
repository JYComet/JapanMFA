"""Strict YAML loading and application of per-occurrence reading overrides."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping

import yaml

from japanmfa.domain import Token
from japanmfa.errors import StageFailure

from .japanese import normalize_katakana


@dataclass(frozen=True)
class ReadingOverride:
    span: tuple[int, int]
    surface: str
    kana: str


@dataclass(frozen=True)
class ReadingOverrideSet:
    utterances: Mapping[str, tuple[ReadingOverride, ...]]


def _invalid(message: str, **details: object) -> StageFailure:
    return StageFailure("frontend", "invalid_override", f"invalid_override: {message}", details)


def load_reading_overrides(path: Path) -> ReadingOverrideSet:
    """Load the documented ``utterances.<id>.readings`` YAML structure."""
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise _invalid(f"could not load reading overrides: {path}", error=str(exc)) from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("utterances"), dict):
        raise _invalid("overrides must contain an utterances mapping")

    parsed: dict[str, tuple[ReadingOverride, ...]] = {}
    for utterance_id, value in raw["utterances"].items():
        if not isinstance(utterance_id, str) or not utterance_id:
            raise _invalid("utterance IDs must be non-empty strings")
        if not isinstance(value, dict) or not isinstance(value.get("readings"), list):
            raise _invalid(
                "each utterance must contain a readings list", utterance_id=utterance_id
            )
        entries: list[ReadingOverride] = []
        for item in value["readings"]:
            if not isinstance(item, dict):
                raise _invalid("each reading override must be a mapping", utterance_id=utterance_id)
            if set(item) != {"span", "surface", "kana"}:
                raise _invalid(
                    "each reading override must contain only span, surface, and kana",
                    utterance_id=utterance_id,
                )
            span = item["span"]
            if (
                not isinstance(span, (list, tuple))
                or len(span) != 2
                or any(isinstance(part, bool) or not isinstance(part, int) for part in span)
            ):
                raise _invalid(
                    "override span must be a [start, end] integer pair",
                    utterance_id=utterance_id,
                )
            surface = item["surface"]
            kana = item["kana"]
            if not isinstance(surface, str) or not surface:
                raise _invalid("override surface must be a non-empty string", utterance_id=utterance_id)
            if not isinstance(kana, str) or not kana:
                raise _invalid("override kana must be a non-empty string", utterance_id=utterance_id)
            normalized = normalize_katakana(kana)
            entries.append(ReadingOverride((span[0], span[1]), surface, normalized))
        parsed[utterance_id] = tuple(entries)
    return ReadingOverrideSet(parsed)


def apply_reading_overrides(
    utterance_id: str,
    original: str,
    tokens: tuple[Token, ...],
    overrides: ReadingOverrideSet,
) -> tuple[Token, ...]:
    """Validate every selected override, then apply all changes atomically."""
    selected = tuple(overrides.utterances.get(utterance_id, ()))
    if not selected:
        return tokens

    validated: list[tuple[int, str]] = []
    seen_spans: set[tuple[int, int]] = set()
    ordered = sorted(selected, key=lambda item: item.span)
    previous_end = -1
    for override in ordered:
        start, end = override.span
        if (start, end) in seen_spans:
            raise StageFailure(
                "frontend",
                "duplicate_override",
                "duplicate_override: duplicate reading override span",
                {"utterance_id": utterance_id, "span": [start, end]},
            )
        seen_spans.add((start, end))
        if start < 0 or end <= start or end > len(original):
            raise _invalid(
                "override span is outside the source text",
                utterance_id=utterance_id,
                span=[start, end],
            )
        if start < previous_end:
            raise StageFailure(
                "frontend",
                "overlapping_overrides",
                "overlapping_overrides: reading override spans overlap",
                {"utterance_id": utterance_id, "span": [start, end]},
            )
        previous_end = end
        if original[start:end] != override.surface:
            raise StageFailure(
                "frontend",
                "override_surface_mismatch",
                "override_surface_mismatch: override surface does not match the source span",
                {"utterance_id": utterance_id, "span": [start, end]},
            )
        if not all("ァ" <= character <= "ヿ" or character == "ー" for character in override.kana):
            raise StageFailure(
                "frontend",
                "invalid_override_kana",
                "invalid_override_kana: override kana must normalize to katakana",
                {"utterance_id": utterance_id, "kana": override.kana},
            )
        matches = [token for token in tokens if token.start == start and token.end == end]
        if len(matches) != 1 or matches[0].surface != override.surface:
            raise StageFailure(
                "frontend",
                "override_requires_complete_token",
                "override_requires_complete_token: boundaries must match one complete token",
                {"utterance_id": utterance_id, "span": [start, end]},
            )
        validated.append((matches[0].index, override.kana))

    changes = dict(validated)
    return tuple(
        replace(token, reading=changes[token.index], reading_source="override")
        if token.index in changes
        else token
        for token in tokens
    )
