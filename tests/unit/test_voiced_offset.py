import numpy as np
import pytest
import soundfile as sf

from japanmfa.domain import PhoneAnnotation, PhoneInterval
from japanmfa.postprocess import postprocess_annotations


def _phone(start, end, label):
    return PhoneAnnotation(PhoneInterval(start, end, label), 0, (), 'エ', 'HH', False)


def _audio(path, active_end):
    t = np.arange(16000 * 2) / 16000
    sf.write(path, np.where((t >= .5) & (t < active_end),
                           .2 * np.sin(2 * np.pi * 200 * t), 0.), 16000, subtype='PCM_16')


def test_trailing_voiced_vowel_releases_measured_quiet_frames(tmp_path):
    audio = tmp_path / 'offset.wav'
    _audio(audio, 1.08)
    result = postprocess_annotations(audio, 2., (_phone(.5, .97, 'a'), _phone(.97, 1.10, 'e')))
    speech = [p for p in result.annotations if not p.is_silence]
    assert speech[-1].interval.end == pytest.approx(1.08)
    assert speech[0].interval.end == .97
    assert any(x['reason'] == 'energy_voiced_offset_trim' for x in result.report['edits'])


@pytest.mark.parametrize('label', ['i', 'ɨ', 'ɯ', 't'])
def test_offset_trim_does_not_infer_devoiced_vowel_or_stop_end(tmp_path, label):
    audio = tmp_path / 'devoiced.wav'
    _audio(audio, 1.08)
    result = postprocess_annotations(audio, 2., (_phone(.5, 1.10, label),))
    assert next(p for p in result.annotations if not p.is_silence).interval.end == 1.10


def test_offset_trim_never_moves_an_internal_phone_boundary(tmp_path):
    audio = tmp_path / 'internal.wav'
    _audio(audio, 1.02)
    result = postprocess_annotations(audio, 2., (_phone(.5, 1.10, 'e'), _phone(1.10, 1.3, 't')))
    assert next(p for p in result.annotations if not p.is_silence).interval.end == 1.10


def test_offset_trim_tolerates_one_weak_frame_before_confirmed_quiet(tmp_path):
    audio = tmp_path / 'decaying.wav'
    _audio(audio, 1.08)
    samples, rate = sf.read(audio)
    samples[round(1.06 * rate):round(1.07 * rate)] = 0.
    sf.write(audio, samples, rate, subtype='PCM_16')
    result = postprocess_annotations(audio, 2., (_phone(.5, 1.10, 'aː'),))
    assert next(p for p in result.annotations if not p.is_silence).interval.end == pytest.approx(1.08)
