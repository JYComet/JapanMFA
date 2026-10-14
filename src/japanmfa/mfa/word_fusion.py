"""Conservative acoustic arbitration of MFA words against Qwen word anchors."""

from __future__ import annotations

import wave
from dataclasses import replace
from pathlib import Path
from typing import Sequence

import numpy as np

from japanmfa.asr.qwen3 import Timestamp
from japanmfa.asr.timestamps import _lexical
from japanmfa.domain import Token
from japanmfa.mfa.textgrid import MfaAlignment, MfaPhone, MfaWord


def _ctc_by_source_span(text: str, lexical: Sequence[Timestamp]) -> dict[tuple[int, int], Timestamp]:
    positions = [index for index, char in enumerate(text) if _lexical(char)]
    spans: dict[tuple[int, int], Timestamp] = {}
    cursor = 0
    for item in lexical:
        width = sum(_lexical(char) for char in item.text)
        if width <= 0 or cursor + width > len(positions):
            return {}
        spans[(positions[cursor], positions[cursor + width - 1] + 1)] = item
        cursor += width
    return spans if cursor == len(positions) else {}


def _rms_frames(audio_path: Path) -> tuple[np.ndarray, float]:
    with wave.open(str(audio_path), "rb") as wav:
        rate = wav.getframerate()
        if rate <= 0 or wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise ValueError("word fusion requires mono PCM16 audio")
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(np.float64) / 32768
    frame = max(1, round(rate * .01))
    count = len(samples) // frame
    rms = np.sqrt(np.mean(samples[:count * frame].reshape(count, frame) ** 2, axis=1))
    return rms, frame / rate


def _edge_supported(
    rms: np.ndarray, frame_seconds: float, old: float, new: float,
    *, inward: bool, threshold: float,
) -> bool:
    low, high = min(old, new), max(old, new)
    starts = np.arange(len(rms)) * frame_seconds
    measured = rms[(starts + frame_seconds > low + 1e-9) & (starts < high - 1e-9)]
    if len(measured) < 2:
        return False
    if inward:
        return bool(np.all(measured < threshold))
    active = measured > threshold
    if active.mean() < .8 or not active[0] or not active[-1]:
        return False
    return bool(np.all(np.convolve((~active).astype(int), np.ones(3, dtype=int), "valid") < 3))


def _rescale_phones(
    phones: Sequence[MfaPhone], old: MfaWord, start: float, end: float,
) -> tuple[MfaPhone, ...] | None:
    owned = [phone for phone in phones if not phone.is_silence and phone.word_alias == old.alias]
    if not owned or min(phone.start for phone in owned) < old.start - 1e-6 \
            or max(phone.end for phone in owned) > old.end + 1e-6:
        return None
    scale = (end - start) / (old.end - old.start)
    if not .75 - 1e-6 <= scale <= 1.25 + 1e-6:
        return None
    result = []
    for phone in owned:
        a = round(start + (phone.start - old.start) * scale, 6)
        b = round(start + (phone.end - old.start) * scale, 6)
        if b - a < .005 - 1e-6:
            return None
        result.append(replace(phone, start=a, end=b))
    return tuple(result)


def fuse_word_boundaries(
    alignment: MfaAlignment, source: str, tokens: Sequence[Token],
    lexical: Sequence[Timestamp], audio_path: Path,
) -> tuple[MfaAlignment, dict[str, object]]:
    """Move only acoustically supported 0.15–0.30 s edges; retain raw provenance."""
    if len(tokens) != len(alignment.words):
        raise ValueError("word fusion requires one MFA word per locked token")
    anchors = _ctc_by_source_span(source, lexical)
    rms, frame_seconds = _rms_frames(audio_path)
    threshold = max(.001, 3 * float(np.percentile(rms, 15))) if len(rms) else .001
    words = list(alignment.words)
    phones = list(alignment.phones)
    edits: list[dict[str, object]] = []
    conflicts: list[dict[str, object]] = []
    matched = 0
    for index, (token, original) in enumerate(zip(tokens, alignment.words)):
        anchor = anchors.get((token.start, token.end))
        if anchor is None:
            continue
        matched += 1
        if anchor.end <= anchor.start:
            conflicts.append({"token_index": index, "reason": "zero_duration_ctc"})
            continue
        proposed = [words[index].start, words[index].end]
        edge_edits: list[dict[str, object]] = []
        for edge_index, (ctc_time, old_time) in enumerate(
            ((anchor.start, original.start), (anchor.end, original.end))
        ):
            difference = ctc_time - old_time
            if abs(difference) > .30 + 1e-9:
                conflicts.append({"token_index": index, "edge": "start" if edge_index == 0 else "end",
                                  "reason": "large_drift", "difference_seconds": round(difference, 6)})
                continue
            if abs(difference) <= .15 + 1e-9:
                continue
            target = round((ctc_time + old_time) / 2, 6)
            if edge_index == 0:
                if index and target < words[index - 1].end - 1e-9:
                    continue
                inward = target > old_time
            else:
                if index + 1 < len(words) and target > words[index + 1].start + 1e-9:
                    continue
                inward = target < old_time
            if not _edge_supported(rms, frame_seconds, old_time, target,
                                   inward=inward, threshold=threshold):
                continue
            proposed[edge_index] = target
            edge_edits.append({"token_index": index, "edge": "start" if edge_index == 0 else "end",
                               "mfa_seconds": old_time, "ctc_seconds": ctc_time,
                               "resolved_seconds": target, "evidence": "quiet_trim" if inward else "connected_voice"})
        if not edge_edits or proposed[1] <= proposed[0]:
            continue
        mapped = _rescale_phones(phones, original, proposed[0], proposed[1])
        if mapped is None:
            continue
        by_original = {id(phone): phone for phone in phones
                       if not phone.is_silence and phone.word_alias == original.alias}
        replacements = iter(mapped)
        phones = [next(replacements) if id(phone) in by_original else phone for phone in phones]
        words[index] = MfaWord(original.alias, proposed[0], proposed[1])
        edits.extend(edge_edits)
    if not edits:
        return alignment, {"matched_words": matched, "edits": [], "conflicts": conflicts,
                           "threshold": threshold}
    # A word may extend into MFA's old explicit silence; preserve its remainder.
    adjusted: list[MfaPhone] = []
    for phone in phones:
        if not phone.is_silence:
            adjusted.append(phone)
            continue
        start, end = phone.start, phone.end
        for word in words:
            if end <= word.start or start >= word.end:
                continue
            if start < word.start < end <= word.end:
                end = word.start
            elif word.start <= start < word.end < end:
                start = word.end
            elif word.start <= start and end <= word.end:
                start = end
            else:
                # A single silence enclosing a word cannot be safely split here.
                return alignment, {"matched_words": matched, "edits": [],
                                   "conflicts": conflicts + [{"reason": "silence_encloses_word"}],
                                   "threshold": threshold}
        if end - start > 1e-6:
            adjusted.append(replace(phone, start=start, end=end))
    adjusted.sort(key=lambda phone: (phone.start, phone.end))
    return replace(alignment, words=tuple(words), phones=tuple(adjusted)), {
        "matched_words": matched, "edits": edits, "conflicts": conflicts,
        "threshold": threshold,
    }


__all__ = ["fuse_word_boundaries"]
