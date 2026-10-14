"""Audit published phone owners against immutable Qwen and raw MFA edges."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Sequence

import numpy as np
import soundfile as sf

from ..domain import PhoneAnnotation
from .textgrid import MfaAlignment, MfaWord
from .timed import TimedSegment, annotate_timing_report, audit_timed_alignment


def review_processed_timing(
    report: dict[str, object], segments: Sequence[TimedSegment],
    alignment: MfaAlignment, annotations: Sequence[PhoneAnnotation],
    token_indices: Sequence[int], working_audio: Path,
    *, raw_alignment: MfaAlignment | None = None,
) -> None:
    """Keep raw disagreements; gate the geometry actually being published.

    An inward anchor correction is justified only when the entire removed
    span is measured quiet and the retained edge has adjacent active frames.
    This covers padded leading silence without hiding an omitted sound island.
    Acoustic failures already present in the report are never cleared here.
    """
    report['raw_timestamp_alignment'] = {
        'max_drift_seconds': .2,
        'issues': audit_timed_alignment(segments, raw_alignment or alignment),
    }
    if len(token_indices) != len(alignment.words):
        raise ValueError('timing review requires one final owner per MFA word')
    words = []
    for token_index, word in zip(token_indices, alignment.words):
        owned = [p.interval for p in annotations
                 if not p.is_silence and p.token_index == token_index]
        if not owned:
            raise ValueError('timing review is missing a final word owner')
        words.append(MfaWord(word.alias, min(p.start for p in owned), max(p.end for p in owned)))
    issues = audit_timed_alignment(segments, replace(alignment, words=tuple(words)))
    inward = [issue for issue in issues
              if not issue.get('supported_by_audio') and (
                  (issue['edge'] == 'start' and issue['difference_seconds'] > 0)
                  or (issue['edge'] == 'end' and issue['difference_seconds'] < 0))]
    if inward:
        audio, rate = sf.read(working_audio, dtype='float64')
        if audio.ndim != 1:
            raise ValueError('timing review requires mono audio')
        frame = max(1, round(rate * .01))
        count = len(audio) // frame
        rms = np.sqrt(np.mean(audio[:count * frame].reshape(count, frame) ** 2, axis=1))
        if len(rms):
            threshold = max(.001, 3 * float(np.percentile(rms, 15)))
            starts = np.arange(count) * frame / rate
            ends = starts + frame / rate
            for issue in inward:
                anchor, boundary = float(issue['qwen_seconds']), float(issue['mfa_seconds'])
                low, high = sorted((anchor, boundary))
                # Include partial edge frames: a non-frame-aligned boundary
                # must not conceal a short burst in the omitted interval.
                quiet = rms[(ends > low + 1e-9) & (starts < high - 1e-9)]
                segment = segments[int(issue['segment'])]
                if issue['edge'] == 'start':
                    limit = min(boundary + .08, words[segment.first_token].end)
                    retained = rms[(starts >= boundary - 1e-9) & (ends <= limit + 1e-9)]
                else:
                    limit = max(boundary - .08, words[segment.last_token - 1].start)
                    retained = rms[(starts >= limit - 1e-9) & (ends <= boundary + 1e-9)]
                active = retained > threshold
                if (len(quiet) >= 3 and np.all(quiet < threshold)
                        and len(active) >= 2 and np.any(active[:-1] & active[1:])):
                    issue['supported_by_audio'] = True
                    issue['support_evidence'] = {
                        'method': 'quiet_anchor_trim', 'start': low, 'end': high,
                        'threshold': threshold, 'max_rms': float(quiet.max()),
                        'quiet_frame_count': len(quiet), 'frame_seconds': frame / rate,
                    }
    annotate_timing_report(report, issues)
    report['timestamp_alignment']['geometry'] = 'final_phone_owners'
