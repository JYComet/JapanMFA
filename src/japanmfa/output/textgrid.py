"""Writing and strict validation for the public five-tier TextGrid artifact."""

from __future__ import annotations

import math
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from japanmfa.domain import PhoneAnnotation


_ITEM_RE = re.compile(r"^\s{4}item\s+\[\d+\]:\s*$")
_INTERVAL_RE = re.compile(r"^\s+intervals\s+\[\d+\]:\s*$")
_FIELD_RE = re.compile(r"^\s*(class|name|xmin|xmax|text)\s*=\s*(.*?)\s*$")
_SIZE_RE = re.compile(r"^\s*(?:size|intervals:\s*size)\s*=\s*(\d+)\s*$")
_EXPECTED_TIERS = ("original", "kana", "phones", "phone_kana", "phone_tone")


@dataclass(frozen=True)
class _ParsedInterval:
    start_raw: str
    end_raw: str
    label: str
    start: float
    end: float


@dataclass(frozen=True)
class _ParsedTier:
    name: str
    xmin: float
    xmax: float
    intervals: tuple[_ParsedInterval, ...]


def _error(message: str) -> ValueError:
    return ValueError(f"invalid five-tier TextGrid: {message}")


def _quoted(raw: str, field: str) -> str:
    if len(raw) < 2 or raw[0] != '"' or raw[-1] != '"':
        raise _error(f"{field} is not a quoted string")
    value: list[str] = []
    index = 1
    while index < len(raw) - 1:
        character = raw[index]
        if character == '"':
            if index + 1 >= len(raw) - 1 or raw[index + 1] != '"':
                raise _error(f"{field} contains an unescaped quote")
            value.append('"')
            index += 2
        else:
            value.append(character)
            index += 1
    return "".join(value)


def _number(raw: str, field: str) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise _error(f"{field} is not numeric") from exc
    if not math.isfinite(value):
        raise _error(f"{field} is not finite")
    return value


def _field_map(lines: Sequence[str], fields: set[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in lines:
        match = _FIELD_RE.match(line)
        if match and match.group(1) in fields:
            key, value = match.group(1), match.group(2)
            if key in found:
                raise _error(f"duplicate {key} field")
            found[key] = value
    return found


def _parse(path: Path) -> tuple[float, float, tuple[_ParsedTier, ...]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise _error(f"could not read {path}") from exc

    item_starts = [index for index, line in enumerate(lines) if _ITEM_RE.match(line)]
    if not item_starts:
        raise _error("contains no interval tiers")
    header = lines[: item_starts[0]]
    header_fields = _field_map(header, {"xmin", "xmax"})
    if set(header_fields) != {"xmin", "xmax"}:
        raise _error("header requires xmin and xmax")
    header_start = _number(header_fields["xmin"], "header xmin")
    header_end = _number(header_fields["xmax"], "header xmax")
    declared_sizes = [
        int(match.group(1))
        for line in header
        if (match := re.match(r"^\s*size\s*=\s*(\d+)\s*$", line))
    ]
    if len(declared_sizes) != 1:
        raise _error("header requires exactly one tier size")
    if declared_sizes[0] != 5 or declared_sizes[0] != len(item_starts):
        raise _error("declared tier size does not equal five parsed tiers")

    tiers: list[_ParsedTier] = []
    for item_number, start in enumerate(item_starts):
        stop = item_starts[item_number + 1] if item_number + 1 < len(item_starts) else len(lines)
        block = lines[start:stop]
        interval_starts = [index for index, line in enumerate(block) if _INTERVAL_RE.match(line)]
        tier_fields = _field_map(block[: interval_starts[0] if interval_starts else len(block)], {"class", "name", "xmin", "xmax"})
        if set(tier_fields) != {"class", "name", "xmin", "xmax"}:
            raise _error(f"tier {item_number + 1} is missing fields")
        if _quoted(tier_fields["class"], "tier class") != "IntervalTier":
            raise _error("all tiers must be IntervalTier")
        name = _quoted(tier_fields["name"], "tier name")
        tier_start = _number(tier_fields["xmin"], f"{name} xmin")
        tier_end = _number(tier_fields["xmax"], f"{name} xmax")
        size_matches = [
            int(match.group(1))
            for line in block
            if (match := _SIZE_RE.match(line))
        ]
        if not size_matches:
            raise _error(f"tier {name} is missing interval size")
        interval_size = size_matches[-1]
        intervals: list[_ParsedInterval] = []
        for interval_number, interval_start in enumerate(interval_starts):
            interval_stop = interval_starts[interval_number + 1] if interval_number + 1 < len(interval_starts) else len(block)
            fields = _field_map(block[interval_start:interval_stop], {"xmin", "xmax", "text"})
            if set(fields) != {"xmin", "xmax", "text"}:
                raise _error(f"{name} interval {interval_number + 1} is missing fields")
            start_raw, end_raw = fields["xmin"], fields["xmax"]
            start_value = _number(start_raw, f"{name} interval xmin")
            end_value = _number(end_raw, f"{name} interval xmax")
            intervals.append(
                _ParsedInterval(
                    start_raw,
                    end_raw,
                    _quoted(fields["text"], "interval text"),
                    start_value,
                    end_value,
                )
            )
        if interval_size != len(intervals):
            raise _error(f"{name} interval size does not match entries")
        tiers.append(_ParsedTier(name, tier_start, tier_end, tuple(intervals)))
    return header_start, header_end, tuple(tiers)


def _validate_intervals(intervals: Sequence[_ParsedInterval], duration: float, tier: str) -> None:
    previous_start: float | None = None
    previous_end: float | None = None
    for interval in intervals:
        if not 0.0 <= interval.start < interval.end <= duration:
            raise _error(f"{tier} interval is outside duration or non-positive")
        if previous_start is not None and interval.start < previous_start:
            raise _error(f"{tier} intervals are not monotonic")
        if previous_end is not None and interval.start < previous_end:
            raise _error(f"{tier} intervals overlap")
        previous_start, previous_end = interval.start, interval.end


def validate_five_tier_textgrid(
    path: Path,
    duration: float,
    silence_labels: frozenset[str],
) -> None:
    """Re-open and validate a complete five-tier long TextGrid."""
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("duration must be finite and greater than zero")
    if not isinstance(silence_labels, frozenset) or not all(isinstance(label, str) for label in silence_labels):
        raise TypeError("silence_labels must be a frozenset of strings")
    header_start, header_end, tiers = _parse(Path(path))
    if header_start != 0.0 or header_end != duration:
        raise _error("header duration does not match requested duration")
    if tuple(tier.name for tier in tiers) != _EXPECTED_TIERS:
        raise _error(f"tier order must be {_EXPECTED_TIERS!r}")
    if any(tier.xmin != 0.0 or tier.xmax != duration for tier in tiers):
        raise _error("tier duration does not match requested duration")

    original, kana, phones, phone_kana, phone_tone = tiers
    for tier in (original, kana):
        if len(tier.intervals) != 1:
            raise _error(f"{tier.name} must contain exactly one interval")
        interval = tier.intervals[0]
        if interval.start != 0.0 or interval.end != duration:
            raise _error(f"{tier.name} must span the complete duration")

    if not (len(phones.intervals) == len(phone_kana.intervals) == len(phone_tone.intervals)):
        raise _error("phone-level tier counts differ")
    _validate_intervals(phones.intervals, duration, "phones")
    _validate_intervals(phone_kana.intervals, duration, "phone_kana")
    _validate_intervals(phone_tone.intervals, duration, "phone_tone")
    for index, (phone, kana_interval, tone_interval) in enumerate(
        zip(phones.intervals, phone_kana.intervals, phone_tone.intervals)
    ):
        if (phone.start_raw, phone.end_raw) != (kana_interval.start_raw, kana_interval.end_raw) or (
            phone.start_raw,
            phone.end_raw,
        ) != (tone_interval.start_raw, tone_interval.end_raw):
            raise _error(f"phone-level boundaries differ at interval {index + 1}")
        if phone.label in silence_labels:
            if kana_interval.label or tone_interval.label:
                raise _error(f"silence labels are not empty at interval {index + 1}")
        elif not phone.label or not kana_interval.label or not tone_interval.label:
            raise _error(f"non-silence labels are incomplete at interval {index + 1}")


def _float_text(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError("TextGrid boundaries must be finite")
    return repr(float(value))


def _text(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("TextGrid labels must be strings")
    return '"' + value.replace('"', '""') + '"'


def _tier_text(name: str, duration_text: str, intervals: Sequence[tuple[str, str, str]]) -> list[str]:
    lines = [
        '        class = "IntervalTier"',
        f"        name = {_text(name)}",
        "        xmin = 0.0",
        f"        xmax = {duration_text}",
        f"        intervals: size = {len(intervals)}",
    ]
    for index, (start, end, label) in enumerate(intervals, start=1):
        lines.extend(
            [
                f"        intervals [{index}]:",
                f"            xmin = {start}",
                f"            xmax = {end}",
                f"            text = {_text(label)}",
            ]
        )
    return lines


def _render(duration: float, tiers: Sequence[tuple[str, Sequence[tuple[str, str, str]]]]) -> str:
    duration_text = _float_text(duration)
    lines = [
        'File type = "ooTextFile"',
        'Object class = "TextGrid"',
        "",
        "xmin = 0.0",
        f"xmax = {duration_text}",
        "tiers? <exists>",
        f"size = {len(tiers)}",
        "item []:",
    ]
    for index, (name, intervals) in enumerate(tiers, start=1):
        lines.append(f"    item [{index}]:")
        lines.extend(_tier_text(name, duration_text, intervals))
    return "\n".join(lines) + "\n"


def write_five_tier_textgrid(
    path: Path,
    duration: float,
    original: str,
    kana: str,
    annotations: Sequence[PhoneAnnotation],
) -> None:
    """Write, re-open, validate, and atomically publish a five-tier TextGrid."""
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("duration must be finite and greater than zero")
    if not isinstance(original, str) or not isinstance(kana, str):
        raise TypeError("original and kana must be strings")
    if not isinstance(annotations, Sequence):
        raise TypeError("annotations must be a sequence")

    duration_text = _float_text(duration)
    phone_rows: list[tuple[str, str, str, str, str]] = []
    silence_labels: set[str] = set()
    previous_end: float | None = None
    for annotation in annotations:
        if not isinstance(annotation, PhoneAnnotation):
            raise TypeError("annotations must contain PhoneAnnotation values")
        interval = annotation.interval
        start_text, end_text = _float_text(interval.start), _float_text(interval.end)
        if not 0.0 <= interval.start < interval.end <= duration:
            raise ValueError("annotation interval is outside duration or non-positive")
        if previous_end is not None and interval.start < previous_end:
            raise ValueError("annotation intervals overlap or are not monotonic")
        previous_end = interval.end
        if annotation.is_silence:
            silence_labels.add(interval.label)
            if annotation.kana_label or annotation.tone_label:
                raise ValueError("silence annotations must have empty kana and tone labels")
            phone_kana, phone_tone = "", ""
        else:
            if not interval.label or not annotation.kana_label or not annotation.tone_label:
                raise ValueError("non-silence annotations require non-empty labels")
            phone_kana, phone_tone = annotation.kana_label, annotation.tone_label
        phone_rows.append((start_text, end_text, interval.label, phone_kana, phone_tone))

    # All three phone tiers are projected from this one immutable row list.
    tiers = (
        ("original", (("0.0", duration_text, original),)),
        ("kana", (("0.0", duration_text, kana),)),
        ("phones", tuple((start, end, label) for start, end, label, _, _ in phone_rows)),
        ("phone_kana", tuple((start, end, label) for start, end, _, label, _ in phone_rows)),
        ("phone_tone", tuple((start, end, label) for start, end, _, _, label in phone_rows)),
    )
    rendered = _render(duration, tiers)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        validate_five_tier_textgrid(temporary, float(duration), frozenset(silence_labels))
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


__all__ = ["validate_five_tier_textgrid", "write_five_tier_textgrid"]
