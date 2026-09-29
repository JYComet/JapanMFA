from pathlib import Path

import numpy as np
import soundfile as sf

from japanmfa.output.textgrid import _render
from tools.audit_textgrid_pauses import audit


def test_audit_finds_fragmented_mismatched_pause_with_speech(tmp_path: Path) -> None:
    path = tmp_path / 'sample.TextGrid'
    tiers = [('original', (('0.0', '1.0', 'あ。'),)),
             ('kana', (('0.0', '1.0', 'ア。'),)),
             ('words', (('0.0', '0.5', 'あ'), ('0.5', '1.0', '。')))]
    for name, speech in [('phones', 'a'), ('phone_kana', 'ア'), ('phone_tone', 'HH')]:
        tiers.append((name, (('0.0', '0.5', speech), ('0.5', '0.53', '<sp0>'),
                            ('0.53', '1.0', '<sp1>'))))
    path.write_text(_render(1., tiers))
    audio = np.zeros(16000)
    audio[:12000] = .2 * np.sin(2 * np.pi * 200 * np.arange(12000) / 16000)
    sf.write(path.with_suffix('.wav'), audio, 16000, subtype='PCM_16')
    result = audit(path)
    assert result['adjacent_pause_pairs'] == 1
    assert result['punctuation_mismatches'] == 1
    assert result['pauses'][0]['active_seconds'] >= .24
    assert result['suspect_pause_count'] == 1
    assert not result['passed']


def test_audit_accepts_shared_punctuation_after_real_sound_offset(tmp_path: Path) -> None:
    from japanmfa.domain import PhoneAnnotation, PhoneInterval
    from japanmfa.output.textgrid import write_five_tier_textgrid
    path = tmp_path / 'sample.TextGrid'
    annotation = PhoneAnnotation(PhoneInterval(0., .75, 'a'), 0, (), 'ア', 'HH', False)
    write_five_tier_textgrid(path, 1., 'あ。', 'ア。', (annotation,),
                            words=((0., .75, 'あ'), (.75, 1., '。')))
    audio = np.zeros(16000)
    audio[:12000] = .2 * np.sin(2 * np.pi * 200 * np.arange(12000) / 16000)
    sf.write(path.with_suffix('.wav'), audio, 16000, subtype='PCM_16')
    result = audit(path)
    assert result['passed']
    assert result['suspect_pause_count'] == 0
    assert result['pauses'][0]['active_seconds'] == 0


def test_audit_detects_short_clipped_onset_at_pause_edge(tmp_path: Path) -> None:
    from japanmfa.domain import PhoneAnnotation, PhoneInterval
    from japanmfa.output.textgrid import write_five_tier_textgrid
    path = tmp_path / 'onset.TextGrid'
    annotation = PhoneAnnotation(PhoneInterval(.56, .8, 'a'), 0, (), 'ア', 'HH', False)
    write_five_tier_textgrid(path, 1., 'あ', 'ア', (annotation,))
    audio = np.zeros(16000)
    audio[8480:12800] = .2 * np.sin(2 * np.pi * 200 * np.arange(4320) / 16000)
    sf.write(path.with_suffix('.wav'), audio, 16000, subtype='PCM_16')
    result = audit(path)
    assert result['suspect_pause_count'] == 1
    assert not result['passed']
    assert result['pauses'][0]['active_ranges'] == [{'start': .53, 'end': .56}]


def test_audit_cli_reports_missing_tiers_without_aborting_batch(tmp_path: Path) -> None:
    import json
    import os
    import subprocess
    import sys
    tiers = [('original', (('0.0', '1.0', 'あ'),)), ('kana', (('0.0', '1.0', 'ア'),)),
             ('wrong', (('0.0', '1.0', 'a'),)), ('phone_kana', (('0.0', '1.0', 'ア'),)),
             ('phone_tone', (('0.0', '1.0', 'HH'),))]
    for name in ('bad1', 'bad2'):
        (tmp_path / (name + '.TextGrid')).write_text(_render(1., tiers))
    report = tmp_path / 'audit.json'
    result = subprocess.run([sys.executable, 'tools/audit_textgrid_pauses.py', str(tmp_path),
                             '--output', str(report)], env={**os.environ, 'PYTHONPATH': 'src:.'},
                            capture_output=True, text=True)
    assert result.returncode == 1
    assert report.exists(), result.stderr
    payload = json.loads(report.read_text())
    assert payload['files'] == payload['failed'] == 2
