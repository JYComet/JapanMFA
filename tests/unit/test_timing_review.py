from pathlib import Path

import numpy as np
import soundfile as sf

from japanmfa.domain import PhoneAnnotation, PhoneInterval
from japanmfa.mfa.textgrid import MfaAlignment, MfaWord
from japanmfa.mfa.timed import TimedSegment


def _review(tmp_path: Path, *, hidden_sound=False, final_end=1.89, passed=True):
    from japanmfa.mfa.timing_review import review_processed_timing

    rate = 16000
    t = np.arange(rate * 3) / rate
    active = (t >= .5) & (t < 1.89)
    if hidden_sound:
        active |= (t >= .1) & (t < .3)
    samples = np.where(active, .2 * np.sin(2 * np.pi * 200 * t), 0.)
    audio = tmp_path / 'audio.wav'
    sf.write(audio, samples, rate, subtype='PCM_16')
    raw = MfaAlignment((MfaWord('owner', .5, 1.28),), (), ())
    phones = (PhoneAnnotation(PhoneInterval(.5, final_end, 'a'), 7, (), 'ア', 'HH', False),)
    report = {'passed': passed, 'reason_code': None if passed else 'alignment_acoustic_coverage'}
    review_processed_timing(report, (TimedSegment(0., 1.92, 0, 1, 0., 1.92),),
                            raw, phones, (7,), audio)
    return report


def test_repaired_tail_is_audited_while_original_conflict_is_retained(tmp_path):
    report = _review(tmp_path)
    assert report['passed'] is True
    assert len(report['raw_timestamp_alignment']['issues']) == 2
    issues = report['timestamp_alignment']['issues']
    assert len(issues) == 1
    assert issues[0]['edge'] == 'start'
    assert issues[0]['supported_by_audio'] is True
    assert issues[0]['support_evidence']['method'] == 'quiet_anchor_trim'


def test_quiet_trim_cannot_hide_an_unowned_sound_island(tmp_path):
    report = _review(tmp_path, hidden_sound=True)
    assert report['passed'] is False
    assert report['reason_code'] == 'timestamp_mfa_disagreement'
    assert not report['timestamp_alignment']['issues'][0].get('supported_by_audio')


def test_unrepaired_tail_still_fails_even_if_leading_trim_is_supported(tmp_path):
    report = _review(tmp_path, final_end=1.28)
    assert report['passed'] is False
    end = next(x for x in report['timestamp_alignment']['issues'] if x['edge'] == 'end')
    assert not end.get('supported_by_audio')


def test_supported_timing_never_clears_an_acoustic_failure(tmp_path):
    report = _review(tmp_path, passed=False)
    assert report['passed'] is False
    assert report['reason_code'] == 'alignment_acoustic_coverage'


def test_final_extension_beyond_acoustic_support_is_rejected(tmp_path):
    from japanmfa.mfa.timing_review import review_processed_timing

    # Raw MFA agrees; the final exported phone must still be checked.
    raw = MfaAlignment((MfaWord('owner', .5, 1.),), (), ())
    phones = (PhoneAnnotation(PhoneInterval(.5, 1.7, 'a'), 7, (), 'ア', 'HH', False),)
    report = {'passed': True, 'reason_code': None}
    review_processed_timing(report, (TimedSegment(.5, 1.8, 0, 1, .5, 1., None, 1.2),),
                            raw, phones, (7,), tmp_path / 'unused.wav')
    assert report['raw_timestamp_alignment']['issues'] == []
    assert report['passed'] is False
    assert report['timestamp_alignment']['issues'][0]['mfa_seconds'] == 1.7
