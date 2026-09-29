"""Qwen-bounded audio crops for MFA phone alignment."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence
from pathlib import Path
import wave

import numpy as np

from japanmfa.asr.qwen3 import Timestamp
from japanmfa.asr.timestamps import _lexical
from japanmfa.domain import Token
from japanmfa.errors import StageFailure
from japanmfa.mfa.textgrid import MfaAlignment, MfaPhone, MfaWord, RawMfaInterval, parse_mfa_textgrid


@dataclass(frozen=True)
class TimedSegment:
    start: float
    end: float
    first_token: int
    last_token: int  # exclusive
    anchor_start: float | None = None
    anchor_end: float | None = None
    acoustic_start_limit: float | None = None
    acoustic_end_limit: float | None = None


def plan_timed_segments(
    text: str,
    lexical: Sequence[Timestamp],
    tokens: Sequence[Token],
    duration: float,
    *,
    min_segment_duration: float = 0.6,
    min_gap: float = 0.4,
) -> tuple[TimedSegment, ...]:
    """Use Qwen speech edges wherever they also separate locked tokens.

    MFA determines the phones inside each crop. Long pauses always separate
    crops; within continuous speech, short or zero-width items stay with
    neighboring tokens so MFA receives enough context.
    """
    if not tokens or not math.isfinite(duration) or duration <= 0:
        raise StageFailure("mfa", "invalid_timed_input", "MFA timing requires tokens and positive audio duration")
    if not lexical:
        raise StageFailure("mfa", "timestamps_missing", "native Qwen lexical timestamps are required")

    positions = [index for index, character in enumerate(text) if _lexical(character)]
    source_stream = "".join(text[index] for index in positions)
    token_stream = "".join(character for token in tokens for character in token.surface if _lexical(character))
    qwen_stream = "".join(character for item in lexical for character in item.text if _lexical(character))
    if not source_stream or source_stream != token_stream or source_stream != qwen_stream:
        raise StageFailure("mfa", "timestamp_text_mismatch", "Qwen timestamps do not cover the locked MFA text")

    spans: list[tuple[int, int]] = []
    cursor = 0
    previous_end = 0.0
    for item in lexical:
        width = sum(_lexical(character) for character in item.text)
        if not width or not all(math.isfinite(value) for value in (item.start, item.end)):
            raise StageFailure("mfa", "invalid_timestamp", "Qwen lexical timestamp is invalid")
        if item.start < previous_end or item.end < item.start or item.start < 0 or item.end > duration + 0.05:
            raise StageFailure("mfa", "invalid_timestamp", "Qwen lexical timestamps overlap or exceed audio")
        spans.append((positions[cursor], positions[cursor + width - 1] + 1))
        cursor += width
        previous_end = item.end

    candidates: list[tuple[int, int, float]] = []
    for index in range(len(lexical) - 1):
        left, right = lexical[index], lexical[index + 1]
        if left.end <= left.start or right.end <= right.start:
            continue
        next_start = spans[index + 1][0]
        token_boundary = next((j for j, token in enumerate(tokens) if token.start >= next_start), len(tokens))
        if not 0 < token_boundary < len(tokens):
            continue
        if tokens[token_boundary - 1].end > spans[index][1]:
            continue
        candidates.append((token_boundary, index + 1, right.start - left.end))

    hard_cuts = [(token, lexical_index) for token, lexical_index, gap in candidates if gap >= min_gap]
    island_boundaries = [(0, 0), *hard_cuts, (len(tokens), len(lexical))]
    cuts = list(hard_cuts)
    for (first_token, first_lexical), (last_token, last_lexical) in zip(
        island_boundaries, island_boundaries[1:]
    ):
        group_start = first_lexical
        for token_boundary, lexical_boundary, _gap in candidates:
            if not (first_token < token_boundary < last_token
                    and first_lexical < lexical_boundary < last_lexical):
                continue
            left, right = lexical[lexical_boundary - 1], lexical[lexical_boundary]
            if (left.end - lexical[group_start].start < min_segment_duration
                    or lexical[last_lexical - 1].end - right.start < min_segment_duration):
                continue
            cuts.append((token_boundary, lexical_boundary))
            group_start = lexical_boundary

    boundaries = [(0, 0), *sorted(cuts, key=lambda item: item[1]), (len(tokens), len(lexical))]
    result: list[TimedSegment] = []
    for (first, first_lexical), (last, last_lexical) in zip(boundaries, boundaries[1:]):
        anchor_start = lexical[first_lexical].start
        anchor_end = lexical[last_lexical - 1].end
        start = anchor_start
        end = min(duration, anchor_end)
        if end - start < 0.25:
            lower = (
                (lexical[first_lexical - 1].end + anchor_start) / 2
                if first_lexical else 0.0
            )
            upper = (
                (anchor_end + lexical[last_lexical].start) / 2
                if last_lexical < len(lexical) else duration
            )
            start = max(lower, anchor_start - 0.6)
            end = min(duration, upper, anchor_end + 0.6)
        start, end = round(start, 6), round(end, 6)
        if end <= start:
            raise StageFailure("mfa", "invalid_timed_segment", "Qwen timestamp crop has no duration")
        result.append(TimedSegment(
            start, end, first, last,
            anchor_start, anchor_end,
        ))
    return tuple(result)


def expand_timed_segments_with_audio(
    segments: Sequence[TimedSegment], working_audio: Path,
) -> tuple[TimedSegment, ...]:
    """Give MFA real speech at Qwen crop edges without changing Qwen anchors.

    A sustained high-energy run touching an anchor permits more audio. At a
    right edge, a connected low-energy decay may continue that run for at most
    200 ms, provided three quiet frames confirm its end. Context stops at the
    midpoint of a neighboring Qwen gap, so adjacent utterances cannot acquire
    the same sound.
    """
    with wave.open(str(working_audio), "rb") as source:
        rate = source.getframerate()
        if source.getnchannels() != 1 or source.getsampwidth() != 2 or rate <= 0:
            raise StageFailure("mfa", "invalid_working_audio", "timed MFA requires mono PCM16 audio")
        audio = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2").astype(np.float32) / 32768
    frame = max(1, round(rate * .01))
    count = len(audio) // frame
    if not count:
        return tuple(segments)
    rms = np.sqrt(np.mean(audio[:count * frame].reshape(count, frame).astype(np.float64) ** 2, axis=1))
    frame_seconds = frame / rate
    duration = len(audio) / rate
    decay_threshold = max(3 * float(np.percentile(rms, 15)), .001)

    def support(anchor: float, threshold: float, direction: int) -> float | None:
        index = min(count, max(0, round(anchor / frame_seconds)))
        if direction < 0:
            values = rms[max(0, index - round(.6 / frame_seconds)):index][::-1]
        else:
            values = rms[index:min(count, index + round(.6 / frame_seconds))]
        active = values > threshold
        if len(active) < 5 or not any(np.all(active[offset:offset + 5]) for offset in range(min(8, len(active) - 4))):
            return None
        quiet = 0
        last_active = -1
        for offset, value in enumerate(active):
            quiet = 0 if value else quiet + 1
            if value:
                last_active = offset
            if quiet >= 3:
                break
        if last_active < 4:
            return None
        boundary = index - last_active - 1 if direction < 0 else index + last_active + 1
        return round(max(0.0, min(duration, boundary * frame_seconds)), 6)

    def quiet_padding(boundary: float, threshold: float, direction: int, width: float) -> float:
        """Add context only through quiet frames, never through another sound."""
        index = min(count, max(0, round(boundary / frame_seconds)))
        steps = round(width / frame_seconds)
        for step in range(steps):
            frame_index = index + step if direction > 0 else index - step - 1
            if not 0 <= frame_index < count or rms[frame_index] > threshold:
                break
        else:
            step = steps
        return round(max(0.0, min(duration, (index + direction * step) * frame_seconds)), 6)

    def connected_decay_end(boundary: float, limit: int) -> float | None:
        """Return a connected weak-tail endpoint only after confirmed silence."""
        first = min(count, max(0, round(boundary / frame_seconds)))
        cap = min(count, first + round(.2 / frame_seconds), limit)
        # The 200 ms bound applies to weak activity. Allow three following
        # frames for the required quiet confirmation.
        stop = min(count, cap + 3, limit)
        if first >= stop:
            return None
        quiet = 0
        last_active = -1
        for frame_index in range(first, stop):
            if rms[frame_index] > decay_threshold:
                if frame_index >= cap:
                    return None
                last_active = frame_index
                quiet = 0
            else:
                quiet += 1
                if quiet >= 3:
                    if last_active < first:
                        return None
                    return round((last_active + 1) * frame_seconds, 6)
        # A weak run that reaches the cap without three quiet frames is not a
        # validated endpoint and must not extend acoustic timing support.
        return None

    expanded: list[TimedSegment] = []
    for index, segment in enumerate(segments):
        anchor_start = segment.anchor_start if segment.anchor_start is not None else segment.start
        anchor_end = segment.anchor_end if segment.anchor_end is not None else segment.end
        lo = max(0, min(count, round(anchor_start / frame_seconds)))
        hi = max(lo + 1, min(count, round(anchor_end / frame_seconds)))
        speech_level = float(np.median(rms[lo:hi])) if lo < count else 0.0
        threshold = max(.02, .25 * speech_level)
        start_support = support(anchor_start, threshold, -1)
        end_support = support(anchor_end, threshold, 1)
        end_limit = count
        if index + 1 < len(segments):
            following = segments[index + 1]
            next_start = following.anchor_start if following.anchor_start is not None else following.start
            end_limit = max(0, min(count, round(((anchor_end + next_start) / 2) / frame_seconds)))
        if end_support is not None:
            strong_end = min(end_support, round(end_limit * frame_seconds, 6))
            decay_end = connected_decay_end(strong_end, end_limit)
            end_support = decay_end if decay_end is not None else strong_end
        start = (
            min(segment.start, quiet_padding(start_support, threshold, -1, .1))
            if start_support is not None else segment.start
        )
        end = (
            max(segment.end, quiet_padding(end_support, threshold, 1, .12))
            if end_support is not None else segment.end
        )
        if index:
            previous = segments[index - 1]
            previous_end = previous.anchor_end if previous.anchor_end is not None else previous.end
            start = max(start, (previous_end + anchor_start) / 2)
        if index + 1 < len(segments):
            end = min(end, (anchor_end + next_start) / 2)
        expanded.append(TimedSegment(
            round(max(0.0, start), 6), round(min(duration, end), 6),
            segment.first_token, segment.last_token, segment.anchor_start, segment.anchor_end,
            start_support, end_support,
        ))
    return tuple(expanded)


def align_timed_segments(
    segments: Sequence[TimedSegment],
    working_audio: Path,
    utterance_id: str,
    aliases: Sequence[str],
    dictionary: Path,
    mfa_root: Path,
    runner: Any,
    silence_labels: frozenset[str],
) -> tuple[MfaAlignment, tuple[Path, ...]]:
    """Align each Qwen-bounded crop with MFA, then restore global timestamps."""
    words: list[MfaWord] = []
    phones: list[MfaPhone] = []
    diagnostics: list[RawMfaInterval] = []
    grids: list[Path] = []
    with wave.open(str(working_audio), "rb") as source:
        rate = source.getframerate()
        total_frames = source.getnframes()
        channels = source.getnchannels()
        width = source.getsampwidth()
        if channels != 1 or width != 2 or rate <= 0:
            raise StageFailure("mfa", "invalid_working_audio", "timed MFA requires mono PCM16 audio")
        for index, segment in enumerate(segments):
            start_frame = max(0, min(total_frames, round(segment.start * rate)))
            end_frame = max(0, min(total_frames, round(segment.end * rate)))
            if end_frame <= start_frame:
                raise StageFailure("mfa", "invalid_timed_segment", "timestamp segment has no audio frames")
            segment_root = mfa_root / "segments" / f"{index:03d}"
            corpus = segment_root / "corpus"
            for candidate in (mfa_root, mfa_root / "segments", segment_root, corpus):
                if candidate.is_symlink():
                    raise StageFailure(
                        "mfa", "path_ownership_invalid",
                        f"timestamp MFA path contains a symlink: {candidate}",
                    )
            corpus.mkdir(parents=True, exist_ok=True)
            (corpus / f"{utterance_id}.lab").write_text(
                " ".join(aliases[segment.first_token:segment.last_token]) + "\n", encoding="utf-8"
            )
            with wave.open(str(corpus / f"{utterance_id}.wav"), "wb") as crop:
                crop.setnchannels(channels)
                crop.setsampwidth(width)
                crop.setframerate(rate)
                source.setpos(start_frame)
                crop.writeframes(source.readframes(end_frame - start_frame))
            grid = Path(runner.align(corpus, dictionary, segment_root / "aligned", segment_root / "work"))
            parsed = parse_mfa_textgrid(grid, silence_labels)
            expected = tuple(aliases[segment.first_token:segment.last_token])
            actual = tuple(word.alias for word in parsed.words)
            if actual != expected:
                raise StageFailure(
                    "mfa", "timestamp_segment_coverage",
                    "MFA segment did not cover its locked occurrence aliases",
                    {"segment": index, "expected": expected, "actual": actual},
                )
            offset = start_frame / rate
            crop_duration = (end_frame - start_frame) / rate
            if any(phone.end > crop_duration + 0.05 for phone in parsed.phones):
                raise StageFailure("mfa", "timestamp_segment_bounds", "MFA phone exceeds timestamp audio crop")
            words.extend(MfaWord(word.alias, round(word.start + offset, 6), round(word.end + offset, 6)) for word in parsed.words)
            phones.extend(MfaPhone(phone.label, round(phone.start + offset, 6), round(phone.end + offset, 6),
                                   phone.word_alias, phone.is_silence) for phone in parsed.phones)
            diagnostics.extend(RawMfaInterval(round(row.start + offset, 6), round(row.end + offset, 6),
                                              row.label, row.tier_name) for row in parsed.diagnostic_intervals)
            grids.append(grid)
    return MfaAlignment(tuple(words), tuple(phones), tuple(diagnostics)), tuple(grids)


def audit_timed_alignment(
    segments: Sequence[TimedSegment], alignment: MfaAlignment, *, max_drift: float = 0.2
) -> list[dict[str, object]]:
    """Identify MFA speech edges that disagree materially with Qwen anchors."""
    issues: list[dict[str, object]] = []
    for index, segment in enumerate(segments):
        if segment.anchor_start is None or segment.anchor_end is None:
            continue
        words = alignment.words[segment.first_token:segment.last_token]
        if not words:
            issues.append({"segment": index, "edge": "coverage", "reason": "no_mfa_words"})
            continue
        for edge, qwen_time, mfa_time in (
            ("start", segment.anchor_start, words[0].start),
            ("end", segment.anchor_end, words[-1].end),
        ):
            difference = round(mfa_time - qwen_time, 6)
            if abs(difference) > max_drift:
                supported = (
                    edge == "end" and difference > 0 and segment.acoustic_end_limit is not None
                    and mfa_time <= segment.acoustic_end_limit + .01
                ) or (
                    edge == "start" and difference < 0 and segment.acoustic_start_limit is not None
                    and mfa_time >= segment.acoustic_start_limit - .01
                )
                issue: dict[str, object] = {
                    "segment": index, "edge": edge, "qwen_seconds": qwen_time,
                    "mfa_seconds": round(mfa_time, 6), "difference_seconds": difference,
                }
                if supported:
                    issue["supported_by_audio"] = True
                issues.append(issue)
    return issues


def annotate_timing_report(report: dict[str, object], issues: list[dict[str, object]]) -> None:
    """Keep the acoustic diagnosis while naming a demonstrated timing error."""
    report["timestamp_alignment"] = {"max_drift_seconds": 0.2, "issues": issues}
    unresolved = [issue for issue in issues if not issue.get("supported_by_audio")]
    if unresolved and report.get("reason_code") in (None, "bgm_suspect"):
        report["acoustic_reason_code"] = report.get("reason_code")
        report["reason_code"] = "timestamp_mfa_disagreement"
        report["passed"] = False
