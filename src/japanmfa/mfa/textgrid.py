"""Strict parsing of the raw long TextGrid emitted by MFA."""

from __future__ import annotations

import ast
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from japanmfa.errors import StageFailure


DEFAULT_WORD_TIER_NAMES = frozenset({"word", "words"})
DEFAULT_PHONE_TIER_NAMES = frozenset({"phone", "phones"})
_TIER_RE = re.compile(r"^\s{4}item\s+\[\d+\]:\s*$")
_INTERVAL_RE = re.compile(r"^\s{8}intervals\s+\[\d+\]:\s*$")
_FIELD_RE = re.compile(r"^\s*(class|name|xmin|xmax|text)\s*=\s*(.*?)\s*$")


def _failure(reason_code: str, message: str, **details: object) -> StageFailure:
    return StageFailure("mfa_parse", reason_code, message, details)


@dataclass(frozen=True)
class RawMfaInterval:
    """One interval as it appeared in an MFA TextGrid tier."""

    start: float
    end: float
    label: str
    tier_name: str

    def __post_init__(self) -> None:
        if not math.isfinite(self.start) or not math.isfinite(self.end):
            raise ValueError("interval boundaries must be finite")
        if self.end < self.start:
            raise ValueError("interval end must not precede its start")
        if not isinstance(self.label, str) or not isinstance(self.tier_name, str):
            raise TypeError("interval labels and tier names must be strings")


@dataclass(frozen=True)
class MfaWord:
    alias: str
    start: float
    end: float

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError("MFA words must have positive duration")


@dataclass(frozen=True)
class MfaPhone:
    label: str
    start: float
    end: float
    word_alias: str | None
    is_silence: bool

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError("MFA phones must have positive duration")


@dataclass(frozen=True)
class MfaAlignment:
    """Validated word/phone intervals and raw diagnostic entries."""

    words: tuple[MfaWord, ...]
    phones: tuple[MfaPhone, ...]
    diagnostic_intervals: tuple[RawMfaInterval, ...]


@dataclass(frozen=True)
class _Tier:
    name: str
    intervals: tuple[RawMfaInterval, ...]


def _quoted(value: str, *, field: str, line_number: int) -> str:
    try:
        parsed = ast.literal_eval(value)
    except (SyntaxError, ValueError) as exc:
        raise _failure(
            "malformed_textgrid",
            f"TextGrid {field} is not a quoted string",
            line_number=line_number,
            value=value,
        ) from exc
    if not isinstance(parsed, str):
        raise _failure(
            "malformed_textgrid",
            f"TextGrid {field} must be a string",
            line_number=line_number,
        )
    return parsed


def _float(value: str, *, field: str, line_number: int) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise _failure(
            "malformed_textgrid",
            f"TextGrid {field} must be numeric",
            line_number=line_number,
            value=value,
        ) from exc
    if not math.isfinite(result):
        raise _failure(
            "malformed_textgrid",
            f"TextGrid {field} must be finite",
            line_number=line_number,
            value=value,
        )
    return result


def _parse_tiers(lines: Sequence[str]) -> tuple[_Tier, ...]:
    starts = [index for index, line in enumerate(lines) if _TIER_RE.match(line)]
    if not starts:
        raise _failure("malformed_textgrid", "TextGrid contains no interval tiers")

    tiers: list[_Tier] = []
    for position, start in enumerate(starts):
        stop = starts[position + 1] if position + 1 < len(starts) else len(lines)
        block = lines[start:stop]
        fields: dict[str, tuple[str, int]] = {}
        for offset, line in enumerate(block):
            match = _FIELD_RE.match(line)
            if match and match.group(1) not in fields:
                fields[match.group(1)] = (match.group(2), start + offset + 1)

        if "class" not in fields or "name" not in fields:
            raise _failure("malformed_textgrid", "TextGrid tier lacks class or name")
        tier_class = _quoted(
            fields["class"][0], field="class", line_number=fields["class"][1]
        )
        tier_name = _quoted(
            fields["name"][0], field="name", line_number=fields["name"][1]
        )
        if tier_class != "IntervalTier" or not tier_name:
            continue

        interval_starts = [
            offset for offset, line in enumerate(block) if _INTERVAL_RE.match(line)
        ]
        intervals: list[RawMfaInterval] = []
        for interval_position, interval_start in enumerate(interval_starts):
            interval_stop = (
                interval_starts[interval_position + 1]
                if interval_position + 1 < len(interval_starts)
                else len(block)
            )
            interval_fields: dict[str, tuple[str, int]] = {}
            for offset in range(interval_start, interval_stop):
                match = _FIELD_RE.match(block[offset])
                if match and match.group(1) in {"xmin", "xmax", "text"}:
                    interval_fields[match.group(1)] = (
                        match.group(2),
                        start + offset + 1,
                    )
            if set(interval_fields) != {"xmin", "xmax", "text"}:
                raise _failure(
                    "malformed_textgrid",
                    "TextGrid interval requires xmin, xmax, and text",
                    tier_name=tier_name,
                    interval_number=interval_position + 1,
                )
            interval_start_value = _float(
                interval_fields["xmin"][0],
                field="xmin",
                line_number=interval_fields["xmin"][1],
            )
            interval_end_value = _float(
                interval_fields["xmax"][0],
                field="xmax",
                line_number=interval_fields["xmax"][1],
            )
            label = _quoted(
                interval_fields["text"][0],
                field="text",
                line_number=interval_fields["text"][1],
            )
            try:
                intervals.append(
                    RawMfaInterval(interval_start_value, interval_end_value, label, tier_name)
                )
            except (TypeError, ValueError) as exc:
                raise _failure(
                    "invalid_boundaries",
                    "TextGrid interval has invalid boundaries",
                    tier_name=tier_name,
                    interval_number=interval_position + 1,
                    start=interval_start_value,
                    end=interval_end_value,
                ) from exc
        tiers.append(_Tier(tier_name, tuple(intervals)))
    return tuple(tiers)


def _select_tier(
    tiers: Sequence[_Tier], names: frozenset[str], *, kind: str
) -> _Tier:
    matches = [tier for tier in tiers if tier.name.casefold() in {name.casefold() for name in names}]
    if not matches:
        raise _failure(
            "missing_tier",
            f"TextGrid has no configured {kind} tier",
            expected_tiers=sorted(names),
            available_tiers=[tier.name for tier in tiers],
        )
    if len(matches) != 1:
        raise _failure(
            "ambiguous_tier",
            f"TextGrid has multiple configured {kind} tiers",
            tiers=[tier.name for tier in matches],
        )
    return matches[0]


def _validate_boundaries(intervals: Sequence[RawMfaInterval]) -> None:
    previous_start: float | None = None
    previous_positive_end: float | None = None
    for interval in intervals:
        if previous_start is not None and interval.start < previous_start:
            raise _failure(
                "invalid_boundaries",
                "TextGrid intervals are in decreasing start order",
                tier_name=interval.tier_name,
                start=interval.start,
                previous_start=previous_start,
            )
        if (
            previous_positive_end is not None
            and interval.end > interval.start
            and interval.start < previous_positive_end
        ):
            raise _failure(
                "invalid_boundaries",
                "TextGrid intervals overlap",
                tier_name=interval.tier_name,
                start=interval.start,
                previous_end=previous_positive_end,
            )
        previous_start = interval.start
        if interval.end > interval.start:
            previous_positive_end = interval.end


def _raw_is_diagnostic(interval: RawMfaInterval) -> bool:
    return not interval.label or interval.end == interval.start


def parse_mfa_textgrid(
    path: Path,
    silence_labels: frozenset[str],
    *,
    word_tier_names: frozenset[str] = DEFAULT_WORD_TIER_NAMES,
    phone_tier_names: frozenset[str] = DEFAULT_PHONE_TIER_NAMES,
) -> MfaAlignment:
    """Parse configured MFA word/phone tiers without altering raw boundaries."""
    path = Path(path)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise _failure(
            "textgrid_read_failed",
            f"could not read MFA TextGrid: {path}",
            path=str(path),
            error=str(exc),
        ) from exc

    tiers = _parse_tiers(lines)
    word_tier = _select_tier(tiers, frozenset(word_tier_names), kind="word")
    phone_tier = _select_tier(tiers, frozenset(phone_tier_names), kind="phone")
    _validate_boundaries(word_tier.intervals)
    _validate_boundaries(phone_tier.intervals)
    silence = frozenset(silence_labels)

    diagnostics: list[RawMfaInterval] = []
    words: list[MfaWord] = []
    for interval in word_tier.intervals:
        if _raw_is_diagnostic(interval):
            diagnostics.append(interval)
            continue
        try:
            words.append(MfaWord(interval.label, interval.start, interval.end))
        except ValueError as exc:  # pragma: no cover - guarded above
            raise _failure(
                "invalid_boundaries",
                "MFA word interval must have positive duration",
                tier_name=interval.tier_name,
            ) from exc

    phones: list[MfaPhone] = []
    for interval in phone_tier.intervals:
        is_silence = not interval.label or interval.label in silence
        if interval.end == interval.start:
            if interval.end == interval.start and interval.label and not is_silence:
                raise _failure(
                    "zero_duration_phone",
                    "non-silence MFA phone has zero duration",
                    label=interval.label,
                    start=interval.start,
                    end=interval.end,
                )
            diagnostics.append(interval)
            continue

        if is_silence:
            phones.append(MfaPhone(interval.label, interval.start, interval.end, None, True))
            continue

        containing = [
            word
            for word in words
            if interval.start >= word.start and interval.end <= word.end
        ]
        if len(containing) != 1:
            overlaps = [
                word
                for word in words
                if interval.start < word.end and interval.end > word.start
            ]
            reason = "phone_word_overlap" if len(overlaps) > 1 else "phone_not_contained"
            raise _failure(
                reason,
                "non-silence MFA phone is not contained by exactly one word",
                label=interval.label,
                start=interval.start,
                end=interval.end,
                matching_words=[word.alias for word in containing],
                overlapping_words=[word.alias for word in overlaps],
            )
        phones.append(
            MfaPhone(interval.label, interval.start, interval.end, containing[0].alias, False)
        )

    return MfaAlignment(tuple(words), tuple(phones), tuple(diagnostics))


__all__ = [
    "DEFAULT_PHONE_TIER_NAMES",
    "DEFAULT_WORD_TIER_NAMES",
    "MfaAlignment",
    "MfaPhone",
    "MfaWord",
    "RawMfaInterval",
    "parse_mfa_textgrid",
]
