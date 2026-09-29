"""Use existing Qwen word TextGrids on the original WAV time axis."""

from __future__ import annotations

import hashlib
import math
import os
import shutil
import wave
from pathlib import Path
from typing import Mapping, Sequence

from praatio import textgrid

from japanmfa.asr.qwen3 import ASRResult, Timestamp
from japanmfa.asr.timestamps import _lexical
from japanmfa.audio import AudioInfo
from japanmfa.errors import StageFailure


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read_ctc_words(path: Path, reference: str, duration: float) -> tuple[Timestamp, ...]:
    """Validate the complete CTC word and zero-width point stream."""
    grid = textgrid.openTextgrid(str(path), includeEmptyIntervals=True)
    if set(grid.tierNames) != {'words', 'zero_duration'}:
        raise ValueError(f'CTC TextGrid needs words and zero_duration tiers: {path}')
    if abs(grid.maxTimestamp - duration) > max(1 / 16000, 1e-6):
        raise ValueError(f'CTC duration does not match WAV duration: {path}')
    words = grid.getTier('words')
    points = grid.getTier('zero_duration')
    if not isinstance(words, textgrid.IntervalTier) or not isinstance(points, textgrid.PointTier):
        raise ValueError(f'CTC TextGrid tier types are invalid: {path}')
    items = [Timestamp(row.label, row.start, row.end, 'precomputed_ctc')
             for row in words.entries if row.label]
    items.extend(Timestamp(row.label, row.time, row.time, 'precomputed_ctc_zero_duration')
                 for row in points.entries if row.label)
    items.sort(key=lambda row: (row.start, row.end))
    previous_end = 0.0
    for row in items:
        if (not row.text or not math.isfinite(row.start) or not math.isfinite(row.end)
                or row.start < previous_end - 1e-8 or row.end < row.start
                or row.start < 0 or row.end > duration + 1 / 16000):
            raise ValueError(f'CTC words overlap or exceed WAV duration: {path}')
        previous_end = row.end
    expected = ''.join(char for char in reference if _lexical(char))
    actual = ''.join(char for row in items for char in row.text if _lexical(char))
    if not expected or expected != actual:
        raise ValueError(f'CTC lexical text differs from TXT: {path}; expected={expected!r}, got={actual!r}')
    return tuple(items)


class OriginalAxisWav:
    """Copy canonical WAV samples exactly; any changed frame axis is an error."""

    def prepare(self, source: Path, destination: Path) -> AudioInfo:
        source, destination = Path(source), Path(destination)
        try:
            with wave.open(str(source), 'rb') as audio:
                channels, width, rate, frames = (audio.getnchannels(), audio.getsampwidth(),
                                                 audio.getframerate(), audio.getnframes())
                compression = audio.getcomptype()
        except (OSError, EOFError, wave.Error) as exc:
            raise StageFailure('audio', 'invalid_ctc_wav', f'cannot read WAV: {source}') from exc
        if (channels, width, rate, compression) != (1, 2, 16000, 'NONE') or frames <= 0:
            raise StageFailure('audio', 'noncanonical_ctc_wav',
                               f'CTC source requires mono PCM16 16 kHz WAV: {source}')
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + '.partial')
        try:
            shutil.copyfile(source, temporary)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        source_hash = _sha(source)
        working_hash = _sha(destination)
        if source_hash != working_hash:
            raise StageFailure('audio', 'ctc_axis_copy_mismatch', f'WAV copy changed: {source}')
        return AudioInfo(source, destination, frames / rate, rate, channels, rate,
                         frames, frames, source_hash, working_hash)


class PrecomputedCTCClient:
    """ASR-compatible adapter for authoritative TXT plus existing Qwen CTC grids."""

    def __init__(self, grids: Mapping[str, Path], reference_texts: Mapping[str, str]) -> None:
        self.grids = {key: str(Path(path).resolve()) for key, path in grids.items()}
        self.grid_sha256 = {key: _sha(Path(path)) for key, path in grids.items()}
        self.reference_texts = dict(reference_texts)
        if set(self.grids) != set(self.reference_texts):
            raise ValueError('CTC grids and TXT references must have identical stems')

    def transcribe(self, audio_paths: Sequence[Path], *,
                   reference_texts: Mapping[Path, str] | None = None) -> dict[Path, ASRResult]:
        results: dict[Path, ASRResult] = {}
        for audio_path in audio_paths:
            audio_path = Path(audio_path)
            stem = audio_path.parent.parent.name if audio_path.name == 'audio.wav' else audio_path.stem
            if stem not in self.grids or (reference_texts is not None
                                          and reference_texts.get(audio_path) != self.reference_texts[stem]):
                raise StageFailure('asr', 'ctc_reference_mismatch',
                                   f'CTC grid/TXT reference missing or changed for {stem}')
            try:
                with wave.open(str(audio_path), 'rb') as audio:
                    duration = audio.getnframes() / audio.getframerate()
                grid_path = Path(self.grids[stem])
                if _sha(grid_path) != self.grid_sha256[stem]:
                    raise ValueError('CTC grid changed after preflight')
                lexical = read_ctc_words(grid_path, self.reference_texts[stem], duration)
            except (OSError, EOFError, wave.Error, ValueError) as exc:
                raise StageFailure('asr', 'invalid_precomputed_ctc', str(exc),
                                   {'stem': stem, 'ctc': self.grids[stem]}) from exc
            results[audio_path] = ASRResult(
                audio_path, 'Japanese', self.reference_texts[stem],
                'precomputed:Qwen3-ForcedAligner-0.6B',
                'Qwen/Qwen3-ForcedAligner-0.6B', self.reference_texts[stem], lexical,
            )
        return results
