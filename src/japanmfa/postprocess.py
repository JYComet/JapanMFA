"""Upstream silence preprocessing and acoustic MFA postprocessing.

Adapted concepts: ASRMFA--Pure scripts/audio_energy.py frame_rms,
noise_floor_from_rms, speech_onset/speech_offset, and postprocess_textgrids.py
find_speech_in_silence, at c2bcdf6ef81f67aa93bf1bf5e4bb5dbfc8278c85.
Only energy-supported edges adjacent to explicit MFA silence are refined.
All other MFA phone edges remain unchanged.
"""

from __future__ import annotations

import array
import math
import sys
import wave
from dataclasses import dataclass, replace
from pathlib import Path

from .domain import PhoneAnnotation, PhoneInterval
from .errors import StageFailure
from .output.textgrid import complete_phone_partition

import numpy as np

AXIS_EPS = 0.003


def _detect_silence_at_beginning_vec(
    wav: np.ndarray, sr: int, silence_threshold: float = 0.01, frame_length: int = 1024
) -> float:
    """Upstream ASRMFA vectorized leading-silence detector."""
    frame_count = len(wav) // frame_length
    if frame_count == 0:
        return 0.0
    frames = wav[:frame_count * frame_length].reshape(frame_count, frame_length)
    rms = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1))
    first_speech = np.argmax(rms >= silence_threshold)
    if first_speech == 0 and rms[0] >= silence_threshold:
        return 0.0
    if first_speech == 0 and np.all(rms < silence_threshold):
        return frame_count * frame_length / sr
    return float(first_speech * frame_length / sr)


def _detect_silence_at_end_vec(
    wav: np.ndarray, sr: int, silence_threshold: float = 0.01, frame_length: int = 1024
) -> float:
    """Upstream ASRMFA vectorized trailing-silence detector."""
    frame_count = len(wav) // frame_length
    if frame_count == 0:
        return 0.0
    frames = wav[:frame_count * frame_length].reshape(frame_count, frame_length)
    rms = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1))
    reversed_rms = rms[::-1]
    first_speech_from_end = np.argmax(reversed_rms >= silence_threshold)
    if first_speech_from_end == 0 and reversed_rms[0] >= silence_threshold:
        return 0.0
    if first_speech_from_end == 0 and np.all(reversed_rms < silence_threshold):
        return frame_count * frame_length / sr
    return float(first_speech_from_end * frame_length / sr)


def normalize_start_end_silence(
    audio: np.ndarray, sr: int, target_silence_sec: float = 0.5,
    silence_threshold: float = 0.01, frame_length: int = 1024,
) -> np.ndarray:
    """Normalize edges using the pinned upstream arithmetic (no tail rescan)."""
    beginning_silence = _detect_silence_at_beginning_vec(
        audio, sr, silence_threshold=silence_threshold, frame_length=frame_length
    )
    end_silence = _detect_silence_at_end_vec(
        audio, sr, silence_threshold=silence_threshold, frame_length=frame_length
    )
    target_samples = int(target_silence_sec * sr)
    beginning_samples = int(beginning_silence * sr)
    end_samples = int(end_silence * sr)
    if beginning_silence > target_silence_sec:
        audio = audio[beginning_samples - target_samples:]
    elif beginning_silence < target_silence_sec:
        pad = target_samples - beginning_samples
        audio = np.concatenate([np.zeros(pad, dtype=np.float32), np.asarray(audio, dtype=np.float32)])
    else:
        audio = np.asarray(audio, dtype=np.float32)
    pad_offset = max(0, target_samples - beginning_samples) if beginning_silence < target_silence_sec else 0
    effective_end = end_silence
    if pad_offset > 0 and beginning_silence < target_silence_sec:
        effective_end = end_silence
    end_samples_actual = int(effective_end * sr)
    if effective_end > target_silence_sec:
        cut = end_samples_actual - target_samples
        audio = audio[:max(0, len(audio) - cut)]
    elif effective_end < target_silence_sec:
        pad = target_samples - end_samples_actual
        audio = np.concatenate([audio, np.zeros(pad, dtype=np.float32)])
    return audio


def search_silence_ranges(
    wav: np.ndarray, sr: int, sil_vol_threshold: float = 0.003,
    sil_len_threshold: float = 0.08,
) -> list[list[int]]:
    """Return sample-index silence ranges using the exact upstream partition."""
    wav_len = wav.shape[0]
    step = int(sr * 0.01)
    n_steps = max(0, wav_len // step)
    if n_steps == 0:
        return []
    frames = wav[:n_steps * step].reshape(n_steps, step)
    sil_labels = np.max(np.abs(frames), axis=1) < sil_vol_threshold
    spk_ranges = []
    spk_start = None
    min_spk_n = 10
    ext_n = 0
    for i in range(n_steps):
        if sil_labels[i]:
            if spk_start is not None and i - spk_start > min_spk_n:
                spk_ranges.append([max(0, spk_start - ext_n), min(n_steps, i + ext_n)])
            spk_start = None
        elif spk_start is None:
            spk_start = i
    if spk_start is not None and n_steps - spk_start > 3:
        spk_ranges.append([max(0, spk_start - ext_n), n_steps])
    sil_ranges = []
    if len(spk_ranges) == 0:
        sil_ranges.append([0, wav_len])
        return sil_ranges
    sil_n = int(sil_len_threshold * sr / step)
    if spk_ranges[0][0] > sil_n:
        sil_ranges.append([0, spk_ranges[0][0]])
    for i in range(1, len(spk_ranges)):
        if spk_ranges[i][0] - spk_ranges[i - 1][1] > sil_n:
            sil_ranges.append([spk_ranges[i - 1][1], spk_ranges[i][0]])
    if n_steps - spk_ranges[-1][1] > sil_n:
        sil_ranges.append([spk_ranges[-1][1], n_steps])
    if not sil_ranges:
        return sil_ranges
    sil_ranges = [[r[0] * step, r[1] * step] for r in sil_ranges]
    sil_ranges[-1][1] = min(sil_ranges[-1][1], wav_len)
    return sil_ranges


def trim_excessive_silence(
    audio: np.ndarray, sr: int, max_silence_sec: float = 1.0,
    sil_vol_threshold: float = 0.003, sil_len_threshold: float = 0.08,
) -> np.ndarray:
    """Trim excessive silence without changing speech or rescanning the tail."""
    sil_ranges = search_silence_ranges(audio, sr, sil_vol_threshold=sil_vol_threshold,
                                       sil_len_threshold=sil_len_threshold)
    max_sil_samples = int(sr * max_silence_sec)
    new_segments = []
    current_pos = 0
    audio_len = len(audio)
    for s_i, e_i in sil_ranges:
        if s_i > current_pos:
            new_segments.append(audio[current_pos:s_i])
        sil_len = e_i - s_i
        if sil_len > 0:
            new_segments.append(audio[s_i:s_i + min(sil_len, max_sil_samples)])
        current_pos = e_i
    if audio_len > current_pos:
        new_segments.append(audio[current_pos:audio_len])
    if not new_segments:
        return audio
    return np.concatenate(new_segments)


@dataclass(frozen=True)
class PostprocessResult:
    annotations: tuple[PhoneAnnotation, ...]
    report: dict[str, object]


def _duration_ticks(seconds: float, end: float | None = None) -> int:
    """Return integer microseconds on the six-decimal serialized axis.

    MFA/TextGrid timestamps are serialized independently.  Subtracting the
    in-memory binary floats first makes a genuine 15 ms interval appear as
    14,999 us at the QC boundary, so endpoint formatting must happen before
    subtraction (the upstream contract).
    """
    start = 0.0 if end is None else seconds
    finish = seconds if end is None else end
    if (isinstance(start, bool) or isinstance(finish, bool)
            or not math.isfinite(float(start)) or not math.isfinite(float(finish))):
        return 0
    start_tick = int(round(float(f"{float(start):.6f}") * 1_000_000))
    end_tick = int(round(float(f"{float(finish):.6f}") * 1_000_000))
    return end_tick - start_tick


def silence_label(duration: float) -> str:
    ticks = _duration_ticks(duration)
    if ticks < 200_000:
        return "<sp0>"
    if ticks < 500_000:
        return "<sp1>"
    if ticks < 1_500_000:
        return "<sp2>"
    return "<sp3>"


def _threshold_ticks(seconds: float) -> int:
    return int(round(float(seconds) * 1_000_000))


def _phone_duration_qc_issues(annotations: tuple[PhoneAnnotation, ...]) -> list[dict[str, object]]:
    """Apply the upstream 15ms speech-phone rule on integer microseconds."""
    issues: list[dict[str, object]] = []
    minimum = _threshold_ticks(.015)
    for index, item in enumerate(annotations):
        if item.is_silence:
            continue
        start, end = item.interval.start, item.interval.end
        if (not math.isfinite(start) or not math.isfinite(end) or end <= start):
            issues.append({"index": index, "label": item.interval.label,
                           "duration_ticks": None, "threshold_ticks": minimum,
                           "reason": "malformed_interval"})
            continue
        ticks = _duration_ticks(start, end)
        if ticks < minimum:
            issues.append({"index": index, "label": item.interval.label,
                           "duration_ticks": ticks, "threshold_ticks": minimum,
                           "reason": "short_phone"})
    return issues


def _structural_issues(duration: float, annotations: tuple[PhoneAnnotation, ...]) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    cursor = 0
    axis = _duration_ticks(duration)
    for index, item in enumerate(annotations):
        start, end = item.interval.start, item.interval.end
        start_ticks, end_ticks = _duration_ticks(start), _duration_ticks(end)
        if not (math.isfinite(start) and math.isfinite(end) and end > start):
            issues.append({"index": index, "reason": "non_positive_or_nonfinite"})
            continue
        if start_ticks < cursor or end_ticks > axis:
            issues.append({"index": index, "reason": "overlap_or_out_of_axis"})
        if start_ticks > cursor:
            issues.append({"index": index, "reason": "uncovered_gap", "start_ticks": cursor, "end_ticks": start_ticks})
        cursor = max(cursor, end_ticks)
    if cursor != axis:
        issues.append({"reason": "incomplete_axis", "covered_ticks": cursor, "axis_ticks": axis})
    return issues


def _reconcile_publication_geometry(duration: float,
                                    annotations: tuple[PhoneAnnotation, ...]) -> tuple[PhoneAnnotation, ...]:
    """Complete the publication axis while preserving every existing edge."""
    return complete_phone_partition(duration, annotations)


def _collect_tier_discontinuities(tier: object, duration: float | None = None) -> list[dict[str, object]]:
    """Collect finite monotonic interval gaps without repairing their edges."""
    intervals = getattr(tier, "intervals", tier if isinstance(tier, (list, tuple)) else ())
    result: list[dict[str, object]] = []
    cursor = 0.0
    for index, interval in enumerate(intervals):
        owner = getattr(interval, "interval", interval)
        start = float(getattr(owner, "xmin", getattr(owner, "start", 0.0)))
        end = float(getattr(owner, "xmax", getattr(owner, "end", 0.0)))
        if not math.isfinite(start) or not math.isfinite(end) or end <= start:
            result.append({"index": index, "reason": "malformed"})
            continue
        if start > cursor + 1e-6:
            result.append({"index": index, "reason": "gap", "start": cursor, "end": start})
        if start < cursor - 1e-6:
            result.append({"index": index, "reason": "overlap", "start": start, "end": cursor})
        cursor = max(cursor, end)
    if duration is not None and cursor < duration - 1e-6:
        result.append({"reason": "tail_gap", "start": cursor, "end": duration})
    return result



def _refine_silence_phone_boundaries(
    audio: np.ndarray, rate: int, annotations: tuple[PhoneAnnotation, ...],
) -> tuple[tuple[PhoneAnnotation, ...], list[dict[str, object]]]:
    """Move only explicit silence/phone edges when 10 ms energy proves leakage.

    This is the Japanese phone-tier adaptation of the old pipeline's energy
    boundary stage: 15th-percentile noise, 3x/0.001 threshold, local windows,
    and a visible energy drop/onset. It never crosses a separate silent run or
    changes an internal phone/phone edge.
    """
    frame = max(1, int(.010 * rate))
    count = len(audio) // frame
    if count < 3:
        return annotations, []
    global_frames = audio[:count * frame].reshape(count, frame).astype(np.float64)
    rms = np.sqrt(np.mean(global_frames ** 2, axis=1) + 1e-12)
    noise = float(np.percentile(rms, 15))
    threshold = max(noise * 3.0, .001)
    rows = list(annotations)
    edits: list[dict[str, object]] = []

    def energy(start: float, end: float) -> np.ndarray:
        first = max(0, min(count, int(math.ceil(start * rate / frame - 1e-9))))
        last = max(first, min(count, int(math.floor(end * rate / frame + 1e-9))))
        return rms[first:last]

    for index in range(len(rows) - 1):
        left, right = rows[index], rows[index + 1]
        old = left.interval.end
        if abs(old - right.interval.start) > 1.0 / rate:
            continue
        if not left.is_silence and right.is_silence:
            # Old word-end refinement looks for a real energy fall. Preserve
            # the explicit silence if the scan has no sustained quiet region.
            if old - left.interval.start < .015 or right.interval.end - old < .05:
                continue
            before = energy(max(left.interval.start, old - .03), old)
            after = energy(old, min(right.interval.end, old + .5))
            if len(before) < 2 or len(after) < 5 or not np.all(before[-2:] > threshold):
                continue
            if not np.all(after[:2] > threshold):
                continue
            quiet = next((offset for offset in range(2, len(after) - 2)
                          if np.all(after[offset:offset + 3] < threshold)), None)
            if quiet is None:
                continue
            boundary = round(old + quiet * frame / rate, 6)
            if boundary - old < .02 or right.interval.end - boundary < .03:
                continue
            rows[index] = replace(left, interval=PhoneInterval(left.interval.start, boundary, left.interval.label))
            rows[index + 1] = replace(right, interval=PhoneInterval(boundary, right.interval.end, right.interval.label))
            edits.append({"index": index, "reason": "energy_tail_extension", "before": old,
                          "after": boundary, "noise_floor": noise, "threshold": threshold})
        elif left.is_silence and not right.is_silence:
            # The old silence-adjacent pull-back is bounded to 120 ms.
            if old - left.interval.start < .05 or right.interval.end - old < .015:
                continue
            before_start = max(left.interval.start, old - .12)
            before = energy(before_start, old)
            after = energy(old, min(right.interval.end, old + .03))
            if len(before) < 5 or len(after) < 2 or not np.all(after[:2] > threshold):
                continue
            if not np.all(before[-2:] > threshold):
                continue
            onset = next((offset + 3 for offset in range(len(before) - 4)
                          if np.all(before[offset:offset + 3] < threshold)
                          and np.all(before[offset + 3:offset + 5] > threshold)), None)
            if onset is None:
                continue
            boundary = round(before_start + onset * frame / rate, 6)
            if old - boundary < .02 or boundary - left.interval.start < .03:
                continue
            rows[index] = replace(left, interval=PhoneInterval(left.interval.start, boundary, left.interval.label))
            rows[index + 1] = replace(right, interval=PhoneInterval(boundary, right.interval.end, right.interval.label))
            edits.append({"index": index + 1, "reason": "energy_onset_pullback", "before": old,
                          "after": boundary, "noise_floor": noise, "threshold": threshold})
    return tuple(rows), edits


def _bgm_suspects(
    audio: np.ndarray,
    rate: int,
    annotations: tuple[PhoneAnnotation, ...],
    *,
    explicit_silence_spans: tuple[tuple[float, float], ...] | None = None,
) -> list[dict[str, object]]:
    """Run the old pipeline's final-boundary 50 ms frame-level BGM scan."""
    if explicit_silence_spans is None:
        silence_spans = [(item.interval.start, item.interval.end) for item in annotations
                         if item.is_silence]
    else:
        silence_spans = [(float(start), float(end)) for start, end in explicit_silence_spans
                         if math.isfinite(float(start)) and math.isfinite(float(end))]
    silence_spans = [(start, end) for start, end in silence_spans if end - start >= .3]
    if not silence_spans:
        return []
    frame = max(1, int(.010 * rate))
    count = len(audio) // frame
    if count:
        frames = audio[:count * frame].reshape(count, frame).astype(np.float64)
        all_rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-12)
        kth = min(count - 1, max(1, int(count * .6)))
        noise = max(float(np.partition(all_rms, kth)[kth]), 1e-6)
    else:
        noise = 1e-6
    threshold = min(max(noise * 2.0, .005), .05)
    speech_energies = []
    for item in annotations:
        if item.is_silence:
            continue
        start = max(0, int(item.interval.start * rate))
        end = min(len(audio), int(item.interval.end * rate))
        if end > start:
            speech_energies.append(float(np.mean(np.abs(audio[start:end]))))
    avg_speech = float(np.mean(speech_energies)) if speech_energies else 0.0
    details: list[dict[str, object]] = []
    total_sil_dur = 0.0
    suspect_dur = 0.0
    scan_frame = max(1, int(.050 * rate))
    hop = max(1, scan_frame // 2)
    for start, end in silence_spans:
        lo = max(0, int(start * rate))
        hi = min(len(audio), int(end * rate))
        if hi <= lo:
            continue
        span_dur = end - start
        total_sil_dur += span_dur
        n_frames = max(1, (hi - lo - scan_frame) // hop + 1)
        values = [float(np.mean(np.abs(audio[lo + offset * hop:min(lo + offset * hop + scan_frame, hi)])))
                  for offset in range(n_frames)]
        high_ratio = sum(value > threshold for value in values) / n_frames
        if high_ratio >= .20:
            details.append({"xmin": start, "xmax": end, "duration": span_dur,
                            "energy": max(values), "high_ratio": round(high_ratio, 3),
                            "noise_floor": noise})
            suspect_dur += span_dur * high_ratio
    if not details or not total_sil_dur or suspect_dur / total_sil_dur <= .1:
        return []
    return [{"rule": "bgm_suspect", "noise_floor": round(noise, 6),
             "avg_speech_energy": round(avg_speech, 6),
             "suspect_intervals": len(details),
             "suspect_ratio": round(suspect_dur / total_sil_dur, 3),
             "total_sil_dur": round(total_sil_dur, 3),
             "suspect_dur": round(suspect_dur, 3), "details": details[:10]}]




def _low_energy_final_vowels(
    audio: np.ndarray, rate: int, annotations: tuple[PhoneAnnotation, ...],
) -> list[dict[str, object]]:
    """Reject a clearly silent final /a,e,o/ after an energetic vowel owner.

    Japanese /i,ɯ/ can devoice, so this narrow diagnostic does not infer
    their timing from energy alone. It catches the observed MFA error where a
    whole word is energetic but its last /e/ is placed after the waveform.
    """
    issues: list[dict[str, object]] = []
    for index, item in enumerate(annotations[:-1]):
        if (item.is_silence or not annotations[index + 1].is_silence
                or item.interval.label.replace("ː", "") not in {"a", "e", "o"}
                or item.interval.end - item.interval.start < .025):
            continue
        prior = [other for other in annotations[:index]
                 if not other.is_silence and other.token_index == item.token_index
                 and other.interval.label.replace("ː", "") in {"a", "e", "o"}]
        if not prior:
            continue
        def rms(owner: PhoneAnnotation) -> float:
            lo = max(0, int(owner.interval.start * rate))
            hi = min(len(audio), int(owner.interval.end * rate))
            segment = audio[lo:hi].astype(np.float64)
            return float(np.sqrt(np.mean(segment ** 2))) if len(segment) else 0.0
        reference = max(rms(other) for other in prior)
        observed = rms(item)
        threshold = max(.001, reference * .02)
        if reference >= .01 and observed < threshold:
            issues.append({"index": index, "label": item.interval.label,
                           "start": item.interval.start, "end": item.interval.end,
                           "rms": observed, "reference_rms": reference,
                           "threshold": threshold})
    return issues


def _unowned_tail_speech_regions(
    audio: np.ndarray, rate: int, annotations: tuple[PhoneAnnotation, ...],
    explicit_silence_spans: tuple[tuple[float, float], ...],
) -> list[dict[str, float]]:
    """Detect a separate sustained sound island after the last MFA speech phone.

    Adapt the old ``find_speech_in_silence`` 5 ms frame, 2.5x local noise,
    15%-of-peak and 40 ms minimum-region rule. A quiet break before the
    island keeps normal word-tail decay from being mistaken for a new word.
    """
    speech = [item for item in annotations if not item.is_silence]
    if not speech:
        return []
    last_end = max(item.interval.end for item in speech)
    frame = max(1, int(.005 * rate))
    minimum_frames = max(1, int(.04 * rate / frame))
    found: list[dict[str, float]] = []
    for start, end in explicit_silence_spans:
        if start < last_end - 1.0 / rate or end - start < .2:
            continue
        lo, hi = max(0, int(start * rate)), min(len(audio), int(end * rate))
        count = (hi - lo) // frame
        if count < minimum_frames * 2:
            continue
        frames = audio[lo:lo + count * frame].reshape(count, frame).astype(np.float64)
        rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-12)
        noise = float(np.median(rms[int(.6 * count):]))
        threshold = max(noise * 2.5, float(np.max(rms)) * .15)
        active = rms > threshold
        quiet_run = 0
        quiet_seen = False
        index = 0
        while index <= count - minimum_frames:
            if not active[index]:
                quiet_run += 1
                quiet_seen = quiet_seen or quiet_run >= minimum_frames
                index += 1
                continue
            run_end = index
            while run_end < count and active[run_end]:
                run_end += 1
            # A new acoustic island must begin after at least 40 ms of
            # measured quiet following the last published speech phone.
            if quiet_seen and run_end - index >= minimum_frames:
                found.append({"xmin": round(start + index * frame / rate, 6),
                              "xmax": round(start + run_end * frame / rate, 6),
                              "silence_start": start, "silence_end": end,
                              "threshold": threshold})
            quiet_run = 0
            index = run_end
    return found


def _rms_frames_in_span(audio: np.ndarray, rate: int, start: float, end: float,
                        frame_ms: float = 10.0) -> tuple[np.ndarray, list[tuple[float, float]]]:
    frame = max(1, int(round(frame_ms / 1000.0 * rate)))
    start_sample = max(0, int(math.ceil(float(start) * rate - 1e-9)))
    end_sample = min(len(audio), int(math.floor(float(end) * rate + 1e-9)))
    first = ((start_sample + frame - 1) // frame) * frame
    last = end_sample - frame
    values: list[float] = []
    positions: list[tuple[float, float]] = []
    for offset in range(first, last + 1, frame):
        segment = audio[offset:offset + frame]
        values.append(float(np.sqrt(np.mean(segment.astype(np.float64) ** 2))))
        positions.append((offset / rate, (offset + frame) / rate))
    return np.asarray(values, dtype=np.float32), positions


def _word_energy_noise_model(audio: np.ndarray, rate: int,
                             silence_spans: tuple[tuple[float, float], ...]) -> dict[str, float | str | int | None]:
    values_list: list[float] = []
    for start, end in silence_spans:
        values, _ = _rms_frames_in_span(audio, rate, start, end, frame_ms=10.0)
        values_list.extend(float(value) for value in values)
    values = np.asarray(values_list, dtype=np.float32)
    source = "explicit_silence_owner" if len(values) else "global_audio_percentile_15"
    if not len(values):
        values, _ = _rms_frames_in_span(audio, rate, 0.0, len(audio) / rate, frame_ms=10.0)
        values = np.sqrt(values.astype(np.float64) ** 2 + 1e-12).astype(np.float32)
    if len(values) == 0:
        percentile = 0.0
    else:
        percentile = float(np.percentile(values, 15))
    return {"source": source, "frame_count": int(len(values)), "frame_ms": 10.0,
            "percentile": 15 if source == "global_audio_percentile_15" else None,
            "noise_floor": percentile, "ratio": 2.0,
            "threshold": percentile * 2.0}


def _word_energy_audit(audio: np.ndarray, rate: int, mfa_alignment: object | None,
                       *, enabled: bool = False,
                       silence_spans: tuple[tuple[float, float], ...] = ()) -> dict[str, object]:
    """Port the upstream immutable word-energy evidence audit.

    ``MfaAlignment`` is the JapanMFA adapter for the upstream words tier:
    raw word spans remain authoritative, and phone ownership is taken only
    from ``word_alias``.  CTC and merge ledgers intentionally remain absent;
    this reports unresolved authority rather than manufacturing either one.
    """
    if mfa_alignment is None:
        return {"schema": "word-energy-evidence-v1", "enabled": enabled,
                "status": "evidence_unavailable", "items": [],
                "reason": "raw MFA alignment was not provided",
                "noise_model": _word_energy_noise_model(audio, rate, silence_spans)}
    words = getattr(mfa_alignment, "words", ())
    phones = getattr(mfa_alignment, "phones", ())
    model = _word_energy_noise_model(audio, rate, silence_spans)
    items: list[dict[str, object]] = []
    # MFA words tier spans the complete working axis even when lexical words
    # begin/end inside it.  Keep edge applicability tied to that serialized
    # tier axis, not to the first/last lexical owner.
    word_axis_start = 0.0
    word_axis_end = len(audio) / rate
    for ordinal, word in enumerate(words):
        owned = [p for p in phones if getattr(p, "word_alias", None) == getattr(word, "alias", None)]
        values, frames = _rms_frames_in_span(audio, rate, float(word.start), float(word.end), frame_ms=10.0)
        rms = float(np.mean(values)) if len(values) else 0.0
        threshold = float(model["threshold"])
        source_spans = [[float(p.start), float(p.end)] for p in owned]
        cursor = float(word.start)
        hole = False
        for start, end in sorted(source_spans):
            if start > cursor + AXIS_EPS:
                hole = True
            cursor = max(cursor, end)
        if cursor < float(word.end) - AXIS_EPS:
            hole = True
        lineage_reason = "phone_hole" if hole else ("phone_owner_missing" if not owned else None)
        premerge_span = [float(word.start), float(word.end)]
        item = {
            "lexical_ordinal": ordinal,
            "word": str(word.alias),
            "final_span": list(premerge_span),
            "premerge_span": list(premerge_span),
            "source_phone_spans": source_spans,
            "ctc_span": None,
            "merge_operation": None,
            "merge_policy": None,
            "english_nvv_adjacency": {
                "previous": None, "next": None, "crossed_silence": False,
            },
            "lineage": {"status": "complete" if owned and not lineage_reason else "unresolved",
                        "reason": lineage_reason,
                        "source_phone_count": len(source_spans),
                        "ctc_boundary_authority": False},
            "rms": {
                "frame_ms": 10.0,
                "premerge_frame_count": int(len(values)),
                "final_frame_count": int(len(values)),
                "premerge_rms": rms,
                "final_rms": rms,
                "active_frame_count": 0,
                "max_continuous_active_frames": 0,
                "frames": [[float(start), float(end)] for start, end in frames],
            },
            "noise_floor": model["noise_floor"],
            "threshold": model["threshold"],
            "classification": "not_applicable",
            "resulting_reason": None,
        }
        source_start = min((span[0] for span in source_spans), default=float(word.start))
        source_end = max((span[1] for span in source_spans), default=float(word.end))
        outside = []
        if source_start < float(word.start) - AXIS_EPS:
            outside.append((source_start, min(source_end, float(word.start))))
        if source_end > float(word.end) + AXIS_EPS:
            outside.append((max(source_start, float(word.end)), source_end))
        mismatch = False
        for outside_start, outside_end in outside:
            outside_values, _ = _rms_frames_in_span(audio, rate, outside_start, outside_end, frame_ms=10.0)
            run = 0
            for value in outside_values:
                run = run + 1 if float(value) > threshold else 0
                if run >= 3:
                    mismatch = True
                    break
        audio_hole = any(start < 0 or end > len(audio) / rate + AXIS_EPS
                         for start, end in source_spans)
        item["diagnostics"] = {
            "source_phone_outside_raw_word": bool(outside),
            "phone_hole": hole,
            "audio_hole": audio_hole,
            "ctc_boundary_authority": False,
            "source_phone_span_count": len(source_spans),
        }
        item["lineage"]["diagnostic_reasons"] = []
        # Upstream ordering is intentional: unresolved ownership/evidence is
        # emitted before any boundary mismatch classification.
        if not owned or hole or audio_hole or not len(values):
            item["classification"] = "word_energy_evidence_unresolved"
            item["resulting_reason"] = "word_energy_evidence_unresolved"
        elif mismatch:
            item["classification"] = "word_energy_boundary_mismatch"
            item["resulting_reason"] = "word_energy_boundary_mismatch"
        elif (float(word.start) <= word_axis_start + AXIS_EPS
              or float(word.end) >= word_axis_end - AXIS_EPS):
            item["classification"] = "not_applicable"
            item["resulting_reason"] = "word_at_audio_edge"
        elif float(np.max(values)) <= 1e-12 or rms < threshold:
            item["classification"] = "true_low_energy"
            item["resulting_reason"] = "word_in_silence"
        else:
            item["classification"] = "energetic"
        active = values > max(threshold, 1e-12)
        item["rms"]["active_frame_count"] = int(np.sum(active))
        run = max_run = 0
        for flag in active:
            run = run + 1 if bool(flag) else 0
            max_run = max(max_run, run)
        item["rms"]["max_continuous_active_frames"] = max_run
        items.append(item)
    return {"schema": "word-energy-evidence-v1", "enabled": enabled,
            "status": "complete", "noise_model": model, "items": items,
            "filter_applied": bool(enabled),
            "ctc_authority": "unavailable", "merge_ledger": []}


def annotation_rows(annotations: tuple[PhoneAnnotation, ...]) -> list[dict[str, object]]:
    return [
        {"start": p.interval.start, "end": p.interval.end, "label": p.interval.label,
         "silence": p.is_silence, "token_index": p.token_index,
         "kana": p.kana_label, "tone": p.tone_label,
         "morae": [{"token_index": m.token_index, "index_in_token": m.index_in_token,
                    "kana": m.kana, "tone": m.tone} for m in p.morae]}
        for p in annotations
    ]


def postprocess_annotations(
    audio_path: Path, duration: float, annotations: tuple[PhoneAnnotation, ...],
    *, mfa_alignment: object | None = None, enable_word_in_silence_filter: bool = False,
) -> PostprocessResult:
    """Run upstream-compatible evidence audits and fill only uncovered gaps.

    Existing MFA phone boundaries remain unchanged. Rejected candidates are
    returned for diagnostics only, never publication.
    """
    try:
        with wave.open(str(audio_path), "rb") as stream:
            if stream.getnchannels() != 1 or stream.getsampwidth() != 2:
                raise ValueError("postprocessing requires mono PCM16 working audio")
            rate = stream.getframerate()
            samples = array.array("h", stream.readframes(stream.getnframes()))
            if sys.byteorder != "little":
                samples.byteswap()
    except (OSError, EOFError, wave.Error, ValueError) as exc:
        raise StageFailure("postprocess", "postprocess_audio_invalid", str(exc)) from exc
    if not samples or not math.isfinite(duration) or duration <= 0:
        raise ValueError("audio and duration must be non-empty and positive")
    tolerance = 1.0 / rate + 1e-6
    if abs(len(samples) / rate - duration) > tolerance:
        raise ValueError("working audio duration differs from source by more than one sample")

    edits: list[dict[str, object]] = []
    adjusted = list(annotations)
    for index, item in enumerate(adjusted):
        if duration < item.interval.end <= duration + tolerance:
            if item.interval.start >= duration:
                raise ValueError("annotation lies outside audio duration")
            adjusted[index] = replace(item, interval=PhoneInterval(item.interval.start, duration, item.interval.label))
            edits.append({"index": index, "reason": "sample_roundoff", "before": item.interval.end, "after": duration})
    # Validate before using geometry in acoustic decisions.
    complete_phone_partition(duration, adjusted)
    audio = np.asarray(samples, dtype=np.float32) / 32768.0
    adjusted, energy_edits = _refine_silence_phone_boundaries(audio, rate, tuple(adjusted))
    edits.extend(energy_edits)
    complete_phone_partition(duration, adjusted)

    size = max(1, round(rate * .005))
    rms = [math.sqrt(sum(v * v for v in samples[i:i + size]) / len(samples[i:i + size])) / 32768.
           for i in range(0, len(samples), size)]
    step = size / rate
    report: dict[str, object] = {
        "version": 2, "reference_commit": "c2bcdf6ef81f67aa93bf1bf5e4bb5dbfc8278c85",
        "method": "upstream_energy_refined_mfa_and_explicit_silence_qc", "frame_seconds": step,
        "sample_rate": rate,
        "raw_phones": annotation_rows(annotations), "edits": edits,
        "tone_source": "tdmelodic_predicted_mora_accent_not_measured_f0",
        "passed": True, "reason_code": None,
    }

    completed = _reconcile_publication_geometry(duration, tuple(adjusted))
    completed_rows: list[PhoneAnnotation] = []
    for item in completed:
        if item.is_silence:
            # The first real leading owner is a structural marker, not a
            # duration bucket.  Keep it as <sp1> for every input length;
            # downstream tiers use the same canonical owner label.
            label = ("<sp1>" if not completed_rows and abs(item.interval.start) <= 1e-9
                     else silence_label(item.interval.end - item.interval.start))
            item = replace(item, interval=PhoneInterval(item.interval.start, item.interval.end, label))
        completed_rows.append(item)
    completed = tuple(completed_rows)
    report["final_phones"] = annotation_rows(completed)
    report["structural_issues"] = _structural_issues(duration, tuple(adjusted))
    report["tier_discontinuities"] = _collect_tier_discontinuities(tuple(adjusted), duration)
    if any(issue.get("reason") in {"non_positive_or_nonfinite", "overlap_or_out_of_axis"}
           for issue in report["structural_issues"]):
        report.update(passed=False, reason_code="structural_invalid")
    report["short_phone_issues"] = _phone_duration_qc_issues(completed)
    if report["short_phone_issues"]:
        report.update(passed=False, reason_code="short_phone")
    report["low_energy_phone_issues"] = _low_energy_final_vowels(audio, rate, completed)
    if report["passed"] and report["low_energy_phone_issues"]:
        report.update(passed=False, reason_code="phone_in_silence")
    raw_silence_spans = tuple(
        (float(item.start), float(item.end))
        for item in getattr(mfa_alignment, "phones", ())
        if bool(getattr(item, "is_silence", False))
    ) if mfa_alignment is not None else ()
    refined_silence_spans = tuple(
        (item.interval.start, item.interval.end)
        for item in adjusted if item.is_silence
    ) if raw_silence_spans else ()
    report["energy_boundary_refinement"] = {
        "edits": energy_edits, "raw_explicit_silence_spans": raw_silence_spans,
        "refined_explicit_silence_spans": refined_silence_spans,
    }
    report["bgm_suspects"] = _bgm_suspects(
        audio, rate, completed,
        explicit_silence_spans=refined_silence_spans,
    )
    report["bgm_diagnostics"] = ([] if raw_silence_spans else [
        {"reason": "explicit_mfa_silence_owner_unavailable",
         "veto": False, "impact": "BGM detector is diagnostic-only for synthesized gaps"}
    ])
    if report["bgm_suspects"]:
        report.update(passed=False, reason_code="bgm_suspect")
    report["unowned_speech_regions"] = _unowned_tail_speech_regions(
        audio, rate, completed, refined_silence_spans,
    )
    if report["passed"] and report["unowned_speech_regions"]:
        report.update(passed=False, reason_code="alignment_acoustic_coverage")
    report["word_energy_audit"] = _word_energy_audit(
        np.asarray(samples, dtype=np.float32) / 32768.0, rate, mfa_alignment,
        enabled=enable_word_in_silence_filter,
        silence_spans=raw_silence_spans,
    )
    if enable_word_in_silence_filter and any(
        item.get("classification") in {"true_low_energy", "word_energy_evidence_unresolved", "word_energy_boundary_mismatch"}
        for item in report["word_energy_audit"].get("items", [])  # type: ignore[union-attr]
    ):
        report.update(passed=False, reason_code="word_in_silence")
    report["blocked_upstream_capabilities"] = [
        {"capability": "_refine_boundaries_by_energy_full_word", "reason": "only explicit silence/phone edges are adapted; timed CTC lexical/punctuation evidence unavailable"},
        {"capability": "CTC_word_boundary_snap", "reason": "timed CTC lexical/punctuation evidence unavailable"},
        {"capability": "merge_short_silences", "reason": "would delete retained MFA phone ownership"},
        {"capability": "fix_short_words", "reason": "Chinese lexical boundary mutation is not applicable"},
        {"capability": "CTC_gap_BGM", "reason": "exact CTC gap evidence unavailable"},
    ]
    return PostprocessResult(completed, report)


def _active_intervals(indices: list[int], step: float, duration: float) -> list[list[float]]:
    spans: list[list[float]] = []
    previous = -2
    for index in indices:
        if index != previous + 1:
            spans.append([index * step, min(duration, (index + 1) * step)])
        else:
            spans[-1][1] = min(duration, (index + 1) * step)
        previous = index
    return spans
