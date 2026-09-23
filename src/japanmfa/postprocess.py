"""Conservative acoustic checks and boundary cleanup for Japanese MFA.

Adapted concepts: ASRMFA--Pure scripts/audio_energy.py frame_rms,
noise_floor_from_rms, speech_onset/speech_offset, and postprocess_textgrids.py
find_speech_in_silence, at c2bcdf6ef81f67aa93bf1bf5e4bb5dbfc8278c85.
Uses normalized PCM16 and the standard library, with no language-specific
word shifting, tone conversion, or Chinese/English dependencies.
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


@dataclass(frozen=True)
class PostprocessResult:
    annotations: tuple[PhoneAnnotation, ...]
    report: dict[str, object]


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
    audio_path: Path, duration: float, annotations: tuple[PhoneAnnotation, ...]
) -> PostprocessResult:
    """Audit acoustic coverage, trim bounded outer margins, fill all gaps.

    A passed report means these checks passed, not that every phone boundary
    or the transcription has been independently verified against the audio.
    Rejected candidates are returned for diagnostics only, never publication.
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

    size = max(1, round(rate * .005))
    rms = [math.sqrt(sum(v * v for v in samples[i:i + size]) / len(samples[i:i + size])) / 32768.
           for i in range(0, len(samples), size)]
    step = size / rate
    peak = max(rms, default=0.)
    noise = sorted(rms)[min(len(rms) - 1, int(len(rms) * .1))]
    # Cap the noise contribution for clips without any quiet lead/trail.
    threshold = max(.001, min(noise * 3., peak * .1), peak * .03)
    active: list[int] = []
    run: list[int] = []
    for index, value in enumerate([*rms, 0.]):
        if value >= threshold:
            run.append(index)
        else:
            if len(run) >= 3:
                active.extend(run)
            run = []

    speech = [i for i, item in enumerate(adjusted) if not item.is_silence]
    report: dict[str, object] = {
        "version": 1, "reference_commit": "c2bcdf6ef81f67aa93bf1bf5e4bb5dbfc8278c85",
        "method": "sustained_frame_rms_conservative_edges", "frame_seconds": step,
        "sample_rate": rate, "noise_floor": noise, "active_threshold": threshold,
        "edge_padding_seconds": .015, "maximum_edge_trim_seconds": .2,
        "maximum_edge_extension_seconds": .08,
        "coverage_boundary_tolerance_seconds": .02,
        "raw_phones": annotation_rows(annotations), "edits": edits,
        "tone_source": "tdmelodic_predicted_mora_accent_not_measured_f0",
        "passed": True, "reason_code": None,
    }
    if not active or not speech:
        report.update(passed=False, reason_code="alignment_no_activity", uncovered_active_seconds=0.)
    else:
        onset, offset = active[0] * step, min(duration, (active[-1] + 1) * step)
        report.update(activity_start=onset, activity_end=offset)
        # Only the outer two edges can be trimmed. Internal MFA boundaries
        # and phone counts remain authoritative; never delete a short phone.
        for index, edge, target in ((speech[0], "start", max(0., onset - .015)),
                                    (speech[-1], "end", min(duration, offset + .015))):
            item = adjusted[index]
            start, end = item.interval.start, item.interval.end
            delta = target - start if edge == "start" else end - target
            remaining = end - target if edge == "start" else target - start
            if ((.005 < delta <= .2) or (-.08 <= delta < -.005)) and remaining >= .02:
                adjusted[index] = replace(item, interval=PhoneInterval(target if edge == "start" else start,
                                                                       target if edge == "end" else end, item.interval.label))
                edits.append({"index": index, "edge": edge, "reason": "outer_silent_margin" if delta > 0 else "nearby_acoustic_edge",
                              "before": start if edge == "start" else end, "after": target})

        # A small extension consumes only adjacent outer silence. No other
        # speech interval is moved; blank remainders are kept explicitly.
        first_start = adjusted[speech[0]].interval.start
        last_end = adjusted[speech[-1]].interval.end
        reconciled: list[PhoneAnnotation] = []
        for index, item in enumerate(adjusted):
            start, end = item.interval.start, item.interval.end
            if item.is_silence and index < speech[0]:
                end = min(end, first_start)
            elif item.is_silence and index > speech[-1]:
                start = max(start, last_end)
            if end > start:
                reconciled.append(replace(item, interval=PhoneInterval(start, end, item.interval.label)))
        adjusted = reconciled

        spans = [p.interval for p in adjusted if not p.is_silence]
        missing = [i for i in active if not any(p.start - .02 <= (i + .5) * step <= p.end + .02 for p in spans)]
        longest = current = 0
        previous = -2
        for index in missing:
            current = current + 1 if index == previous + 1 else 1
            longest, previous = max(longest, current), index
        uncovered = len(missing) * step
        ratio = len(missing) / len(active)
        report.update(uncovered_active_seconds=uncovered, uncovered_active_ratio=ratio,
                      longest_uncovered_seconds=longest * step,
                      active_seconds=len(active) * step,
                      activity_intervals=_active_intervals(active, step, duration))
        if longest * step > .08 or (uncovered > .03 and ratio > .1):
            report.update(passed=False, reason_code="alignment_acoustic_coverage")

    completed = complete_phone_partition(duration, adjusted)
    report["final_phones"] = annotation_rows(completed)
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
