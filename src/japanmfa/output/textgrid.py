"""Writing and strict validation for Japanese word and phone TextGrid artifacts."""

from __future__ import annotations

import math
import os
import re
import tempfile
import unicodedata
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Sequence

from japanmfa.domain import PhoneAnnotation, PhoneInterval, Token
from japanmfa.frontend.japanese import _map_token_spans
from japanmfa.mfa.textgrid import MfaWord


_ITEM_RE = re.compile(r"^\s{4}item\s+\[\d+\]:\s*$")
_INTERVAL_RE = re.compile(r"^\s+intervals\s+\[\d+\]:\s*$")
_FIELD_RE = re.compile(
    r"^\s*(class|name|xmin|xmax|text)\s*=\s*(.*?)\s*$", re.DOTALL
)
_SIZE_RE = re.compile(r"^\s*(?:size|intervals:\s*size)\s*=\s*(\d+)\s*$")
_EXPECTED_TIERS = ("original", "kana", "phones", "phone_kana", "phone_tone")
_EXPECTED_TIERS_WITH_WORDS = ("original", "kana", "words", "phones", "phone_kana", "phone_tone")
_CANONICAL_SILENCE_LABELS = frozenset({"<sp0>", "<sp1>", "<sp2>", "<sp3>"})


def _canonical_silence_label(duration: float, *, leading: bool = False) -> str:
    """Serialize every silence owner with the publication vocabulary."""
    if leading:
        return "<sp1>"
    ticks = round(duration * 1_000_000)
    if ticks < 200_000:
        return "<sp0>"
    if ticks < 500_000:
        return "<sp1>"
    if ticks < 1_500_000:
        return "<sp2>"
    return "<sp3>"


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
    return ValueError(f"invalid TextGrid: {message}")


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


def _logical_lines(text: str) -> tuple[str, ...]:
    """Split a long TextGrid into records without splitting quoted labels.

    Praat's long-text format permits a quoted label to contain physical line
    breaks.  The line breaks are part of the label, so using ``splitlines``
    would both make the field malformed and lose CRLF-versus-LF information.
    Quote escaping uses a doubled quote (``""``), which is handled while
    looking for the closing quote.
    """

    lines: list[str] = []
    start = 0
    in_quote = False
    index = 0
    while index < len(text):
        character = text[index]
        if character == '"':
            if in_quote and index + 1 < len(text) and text[index + 1] == '"':
                index += 2
                continue
            in_quote = not in_quote
            index += 1
            continue
        if not in_quote and character in "\r\n":
            lines.append(text[start:index])
            if (
                character == "\r"
                and index + 1 < len(text)
                and text[index + 1] == "\n"
            ):
                index += 2
            else:
                index += 1
            start = index
            continue
        index += 1
    lines.append(text[start:])
    return tuple(lines)


def _parse(path: Path) -> tuple[float, float, tuple[_ParsedTier, ...]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            lines = _logical_lines(stream.read())
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
    if declared_sizes[0] not in {5, 6} or declared_sizes[0] != len(item_starts):
        raise _error("declared tier size does not equal parsed tiers")

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
    if not intervals or intervals[0].start != 0.0 or intervals[-1].end != duration:
        raise _error(f"{tier} must partition the complete duration")
    previous_start: float | None = None
    previous_end: float | None = None
    for interval in intervals:
        if not 0.0 <= interval.start < interval.end <= duration:
            raise _error(f"{tier} interval is outside duration or non-positive")
        if previous_start is not None and interval.start < previous_start:
            raise _error(f"{tier} intervals are not monotonic")
        if previous_end is not None and interval.start < previous_end:
            raise _error(f"{tier} intervals overlap")
        if previous_end is not None and interval.start != previous_end:
            raise _error(f"{tier} intervals contain an uncovered gap")
        previous_start, previous_end = interval.start, interval.end


def validate_five_tier_textgrid(
    path: Path,
    duration: float,
    silence_labels: frozenset[str],
) -> None:
    """Re-open and validate complete legacy five-tier or production six-tier TextGrid."""
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("duration must be finite and greater than zero")
    if not isinstance(silence_labels, frozenset) or not all(isinstance(label, str) for label in silence_labels):
        raise TypeError("silence_labels must be a frozenset of strings")
    # Canonical postprocessing labels are part of the artifact contract.  A
    # legacy config may only list MFA's input aliases (sil/sp/spn); published
    # <sp0>..<sp3> must still be recognized without requiring config edits.
    silence_labels = frozenset(silence_labels) | frozenset({"<sp0>", "<sp1>", "<sp2>", "<sp3>"})
    header_start, header_end, tiers = _parse(Path(path))
    if header_start != 0.0 or header_end != duration:
        raise _error("header duration does not match requested duration")
    names = tuple(tier.name for tier in tiers)
    if names not in {_EXPECTED_TIERS, _EXPECTED_TIERS_WITH_WORDS}:
        raise _error(f"tier order must be {_EXPECTED_TIERS!r} or {_EXPECTED_TIERS_WITH_WORDS!r}")
    if any(tier.xmin != 0.0 or tier.xmax != duration for tier in tiers):
        raise _error("tier duration does not match requested duration")

    if names == _EXPECTED_TIERS_WITH_WORDS:
        original, kana, words, phones, phone_kana, phone_tone = tiers
        _validate_intervals(words.intervals, duration, "words")
    else:
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
        if not phone.label or phone.label in silence_labels or _source_punctuation(phone.label):
            if kana_interval.label != phone.label or tone_interval.label != phone.label:
                raise _error(f"silence labels are not canonical at interval {index + 1}")
        elif not phone.label or not kana_interval.label or not tone_interval.label:
            raise _error(f"non-silence labels are incomplete at interval {index + 1}")
        elif tone_interval.label not in {"HH", "LL", "HL", "LH"}:
            raise _error(f"non-silence tone must be HH, LL, HL or LH at interval {index + 1}")

    def is_pause(label: str) -> bool:
        return not label or label in silence_labels or bool(_source_punctuation(label))

    for left, right in zip(phones.intervals, phones.intervals[1:]):
        if is_pause(left.label) and is_pause(right.label):
            raise _error("adjacent pause intervals must be coalesced")
    if names == _EXPECTED_TIERS_WITH_WORDS:
        word_pauses = {(row.start, row.end): row.label for row in words.intervals if is_pause(row.label)}
        phone_pauses = {(row.start, row.end): row.label for row in phones.intervals if is_pause(row.label)}
        for span, label in word_pauses.items():
            if phone_pauses.get(span) != label:
                raise _error("word/phone punctuation or pause boundaries differ")
        for span, label in phone_pauses.items():
            if _source_punctuation(label) and word_pauses.get(span) != label:
                raise _error("phone punctuation has no matching word pause")


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


def complete_phone_partition(
    duration: float, annotations: Sequence[PhoneAnnotation]
) -> tuple[PhoneAnnotation, ...]:
    """Fill uncovered time with explicit silence without moving phone edges."""
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("duration must be finite and greater than zero")
    result: list[PhoneAnnotation] = []
    cursor = 0.0
    for annotation in annotations:
        if not isinstance(annotation, PhoneAnnotation):
            raise TypeError("annotations must contain PhoneAnnotation values")
        interval = annotation.interval
        if not (math.isfinite(interval.start) and math.isfinite(interval.end)
                and cursor <= interval.start < interval.end <= duration):
            raise ValueError("annotation intervals overlap or are outside duration")
        if interval.start > cursor:
            result.append(PhoneAnnotation(PhoneInterval(cursor, interval.start, ""), None, (), "", "", True))
        result.append(annotation)
        cursor = interval.end
    if cursor < duration:
        result.append(PhoneAnnotation(PhoneInterval(cursor, duration, ""), None, (), "", "", True))
    return tuple(result)


def _source_punctuation(value: str) -> str:
    """Keep Japanese source punctuation as a single boundary occurrence."""
    significant = "".join(character for character in value if not character.isspace())
    if significant and all(
        unicodedata.category(character).startswith("P") or character in "～〜"
        for character in significant
    ):
        return significant
    return ""


def publication_terminal_text(
    original: str, kana: str, words: Sequence[tuple[float, float, str]],
) -> tuple[str, str, str]:
    """Give an unpunctuated source's real trailing pause a default sentence mark.

    The source transcription stays unchanged upstream.  Only publication text is
    supplemented, and only when the final word interval is an acoustic pause.
    """
    if not words or words[-1][2] not in _CANONICAL_SILENCE_LABELS:
        return original, kana, ""
    if not original.strip() or _source_punctuation(original.rstrip()[-1:]):
        return original, kana, ""
    mark = "。"
    def append_before_trailing_whitespace(value: str) -> str:
        head = value.rstrip()
        return head + mark + value[len(head):]
    return append_before_trailing_whitespace(original), append_before_trailing_whitespace(kana), mark


def publication_phone_partition(
    duration: float, annotations: Sequence[PhoneAnnotation],
    *, words: Sequence[tuple[float, float, str]] | None = None,
) -> tuple[PhoneAnnotation, ...]:
    """Coalesce silence only for publication; keep acoustic provenance upstream."""
    rows: list[PhoneAnnotation] = []
    for item in complete_phone_partition(duration, annotations):
        if item.is_silence and (item.kana_label or item.tone_label):
            raise ValueError("silence annotations must not carry speech labels")
        if item.is_silence and rows and rows[-1].is_silence:
            prior = rows.pop()
            item = replace(prior, interval=PhoneInterval(prior.interval.start, item.interval.end, ""))
        rows.append(item)
    punctuation = {(start, end): label for start, end, label in (words or ())
                   if _source_punctuation(label)}
    return tuple(
        replace(item, interval=PhoneInterval(
            item.interval.start, item.interval.end,
            punctuation.get((item.interval.start, item.interval.end)) or _canonical_silence_label(
                item.interval.end - item.interval.start, leading=item.interval.start == 0.,
            ),
        )) if item.is_silence else item
        for item in rows
    )


def merge_internal_sp0_backward(
    duration: float,
    annotations: Sequence[PhoneAnnotation],
    words: Sequence[tuple[float, float, str]],
) -> tuple[tuple[PhoneAnnotation, ...], tuple[dict[str, object], ...]]:
    """Give each unpunctuated internal ``<sp0>`` to the preceding owner.

    Work from the fully coalesced publication partition, so fragmented MFA
    silence cannot leave another adjacent pause behind.  Source punctuation
    and leading/terminal silence remain their own owners.
    """
    partition = publication_phone_partition(duration, annotations, words=words)
    word_by_span = {(start, end): index for index, (start, end, _) in enumerate(words)}
    merged: list[PhoneAnnotation] = []
    ledger: list[dict[str, object]] = []
    for index, item in enumerate(partition):
        span = (item.interval.start, item.interval.end)
        word_index = word_by_span.get(span)
        between_words = (
            word_index is not None and 0 < word_index < len(words) - 1
            and words[word_index - 1][1] == item.interval.start
            and words[word_index + 1][0] == item.interval.end
            and all(label not in _CANONICAL_SILENCE_LABELS
                    and not _source_punctuation(label)
                    for label in (words[word_index - 1][2], words[word_index + 1][2]))
        )
        inside_word = (
            word_index is None and index + 1 < len(partition)
            and merged and merged[-1].token_index == partition[index + 1].token_index
            and any(start < item.interval.start < item.interval.end < end
                    and label not in _CANONICAL_SILENCE_LABELS
                    and not _source_punctuation(label)
                    for start, end, label in words)
        )
        if (item.interval.label == "<sp0>" and (between_words or inside_word)
                and 0 < index < len(partition) - 1
                and merged and not merged[-1].is_silence
                and not partition[index + 1].is_silence
                and merged[-1].token_index is not None
                and merged[-1].interval.end == item.interval.start
                and partition[index + 1].interval.start == item.interval.end):
            previous = merged.pop()
            merged.append(replace(previous, interval=PhoneInterval(
                previous.interval.start, item.interval.end, previous.interval.label,
            )))
            ledger.append({"start": item.interval.start, "end": item.interval.end,
                           "previous_phone": previous.interval.label,
                           "token_index": previous.token_index})
        else:
            merged.append(item)
    return tuple(merged), tuple(ledger)


def publication_internal_ellipsis(
    original: str,
    kana: str,
    tokens: Sequence[Token],
    words: Sequence[tuple[float, float, str]],
) -> tuple[str, str, tuple[tuple[float, float, str], ...], tuple[dict[str, object], ...]]:
    """Show unpunctuated sentence-internal sp1–sp3 as a shared ellipsis.

    Add marks only to publication text.  The source token spans and raw MFA
    geometry remain unchanged; interval labels are projected to phone tiers by
    ``publication_phone_partition``.
    """
    lexical_rows = [index for index, (_, _, label) in enumerate(words)
                    if label not in _CANONICAL_SILENCE_LABELS and not _source_punctuation(label)]
    if len(lexical_rows) != len(tokens) or any(
        words[row][2] != token.surface for row, token in zip(lexical_rows, tokens)
    ):
        raise ValueError("publication words differ from locked token order")
    insert_after: dict[int, dict[str, object]] = {}
    revised = list(words)
    for ordinal, (left_row, right_row) in enumerate(zip(lexical_rows, lexical_rows[1:])):
        if right_row != left_row + 2:
            continue
        gap_row = left_row + 1
        start, end, label = words[gap_row]
        if label not in {"<sp1>", "<sp2>", "<sp3>"}:
            continue
        revised[gap_row] = (start, end, "……")
        insert_after[ordinal] = {
            "start": start, "end": end,
            "left_lexical_ordinal": ordinal,
            "right_lexical_ordinal": ordinal + 1,
            "prior_label": label, "mark": "……",
        }
    if not insert_after:
        return original, kana, tuple(words), ()
    mapped = _map_token_spans(original, tuple(tokens))
    original_pieces: list[str] = []
    kana_pieces: list[str] = []
    plain_kana_pieces: list[str] = []
    cursor = 0
    for ordinal, (token, (start, end)) in enumerate(mapped):
        gap = original[cursor:start]
        original_pieces.extend((gap, original[start:end]))
        kana_pieces.extend((gap, token.reading))
        plain_kana_pieces.extend((gap, token.reading))
        if ordinal in insert_after:
            original_pieces.append("……")
            kana_pieces.append("……")
        cursor = end
    suffix = original[cursor:]
    original_pieces.append(suffix)
    kana_pieces.append(suffix)
    plain_kana_pieces.append(suffix)
    if "".join(plain_kana_pieces) != kana:
        raise ValueError("publication kana differs from locked token rendering")
    return ("".join(original_pieces), "".join(kana_pieces), tuple(revised),
            tuple(insert_after.values()))


def build_word_intervals(
    duration: float,
    source: str,
    tokens: Sequence[Token],
    aligned_words: Sequence[MfaWord],
    aliases: Sequence[str],
    *, phone_annotations: Sequence[PhoneAnnotation] | None = None,
) -> tuple[tuple[tuple[float, float, str], ...], tuple[str, ...]]:
    """Project source punctuation onto MFA gaps after optional phone refinement."""
    if len(tokens) != len(aliases) or len(aligned_words) != len(aliases):
        raise ValueError("MFA word count differs from locked source token count")
    if not tokens or not 0 < duration < math.inf:
        raise ValueError("word projection requires positive duration and tokens")
    if phone_annotations is not None:
        refined: list[MfaWord] = []
        for token, word in zip(tokens, aligned_words):
            owned = [item.interval for item in phone_annotations
                     if not item.is_silence and item.token_index == token.index]
            if not owned:
                raise ValueError("refined word has no phone owner")
            refined.append(MfaWord(word.alias, min(item.start for item in owned),
                                   max(item.end for item in owned)))
        aligned_words = refined
    rows: list[tuple[float, float, str]] = []
    unplaced: list[str] = []
    cursor = 0.0
    source_end = 0
    for token, word, alias in zip(tokens, aligned_words, aliases):
        if word.alias != alias or not cursor <= word.start < word.end <= duration:
            raise ValueError("MFA word alias or boundaries differ from locked token order")
        if not source_end <= token.start < token.end <= len(source):
            raise ValueError("source token spans are not ordered")
        punctuation = _source_punctuation(source[source_end:token.start])
        if word.start > cursor:
            label = (punctuation if cursor > 0 else "") or _canonical_silence_label(
                word.start - cursor, leading=cursor == 0,
            )
            rows.append((cursor, word.start, label))
        elif punctuation:
            unplaced.append(punctuation)
        rows.append((word.start, word.end, token.surface))
        cursor = word.end
        source_end = token.end
    punctuation = _source_punctuation(source[source_end:])
    if cursor < duration:
        rows.append((cursor, duration, punctuation or _canonical_silence_label(duration - cursor)))
    elif punctuation:
        unplaced.append(punctuation)
    return tuple(rows), tuple(unplaced)


def write_five_tier_textgrid(
    path: Path,
    duration: float,
    original: str,
    kana: str,
    annotations: Sequence[PhoneAnnotation],
    *, words: Sequence[tuple[float, float, str]] | None = None,
) -> None:
    """Write, re-open, validate, and atomically publish a TextGrid."""
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
    for annotation in publication_phone_partition(duration, annotations, words=words):
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
            silence_label = interval.label
            interval = PhoneInterval(interval.start, interval.end, silence_label)
            silence_labels.add(silence_label)
            if annotation.kana_label or annotation.tone_label:
                raise ValueError("silence annotations must not carry speech labels")
            phone_kana, phone_tone = interval.label, interval.label
        else:
            if not interval.label or not annotation.kana_label or not annotation.tone_label:
                raise ValueError("non-silence annotations require non-empty labels")
            phone_kana, phone_tone = annotation.kana_label, annotation.tone_label
            if phone_tone not in {"HH", "LL", "HL", "LH"}:
                raise ValueError("non-silence tone must be HH, LL, HL or LH")
        phone_rows.append((start_text, end_text, interval.label, phone_kana, phone_tone))

    # All three phone tiers are projected from this one immutable row list.
    tiers = (
        ("original", (("0.0", duration_text, original),)),
        ("kana", (("0.0", duration_text, kana),)),
        ("phones", tuple((start, end, label) for start, end, label, _, _ in phone_rows)),
        ("phone_kana", tuple((start, end, label) for start, end, _, label, _ in phone_rows)),
        ("phone_tone", tuple((start, end, label) for start, end, _, _, label in phone_rows)),
    )
    if words is not None:
        word_rows = tuple((_float_text(start), _float_text(end), label)
                          for start, end, label in words)
        tiers = (tiers[0], tiers[1], ("words", word_rows), *tiers[2:])
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


__all__ = ["build_word_intervals", "complete_phone_partition", "publication_phone_partition", "validate_five_tier_textgrid", "write_five_tier_textgrid"]
