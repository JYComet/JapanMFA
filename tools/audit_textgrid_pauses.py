"""Audit published TextGrid/WAV pairs for recurring pause and energy problems.

PYTHONPATH=src:. python tools/audit_textgrid_pauses.py DIRECTORY --output report.json
Exit 1 means a structural or sustained-energy issue needs correction/review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import soundfile as sf

from japanmfa.domain import PhoneAnnotation, PhoneInterval
from japanmfa.postprocess import _pause_acoustic_coverage
from japanmfa.output.textgrid import _parse, _source_punctuation, validate_five_tier_textgrid


def _pause(label: str) -> bool:
    return not label or label.startswith('<sp') or bool(_source_punctuation(label))


def audit(path: Path) -> dict:
    _, duration, parsed = _parse(path)
    tiers = {tier.name: tier for tier in parsed}
    missing = {'original', 'kana', 'phones', 'phone_kana', 'phone_tone'} - tiers.keys()
    if missing:
        raise ValueError(f'missing required tiers: {sorted(missing)}')
    phones = tiers['phones'].intervals
    structural_error = None
    try:
        validate_five_tier_textgrid(path, duration, frozenset())
    except ValueError as exc:
        structural_error = str(exc)
    adjacent = sum(_pause(a.label) and _pause(b.label) for a, b in zip(phones, phones[1:]))
    mismatches = 0
    for word in tiers.get('words', tiers['phones']).intervals:
        if not _pause(word.label):
            continue
        for name in ('phones', 'phone_kana', 'phone_tone'):
            if not any((r.start, r.end, r.label) == (word.start, word.end, word.label)
                       for r in tiers[name].intervals):
                mismatches += 1
                break
    audio_path = path.with_suffix('.wav')
    audio, rate = sf.read(audio_path, dtype='float64')
    if audio.ndim != 1 or abs(len(audio) / rate - duration) > 1 / rate + 1e-6:
        raise ValueError('paired WAV must be mono and match TextGrid duration')
    annotations = tuple(
        PhoneAnnotation(PhoneInterval(row.start, row.end, row.label), None, (), '', '', _pause(row.label))
        for row in phones
    )
    coverage = _pause_acoustic_coverage(audio, rate, annotations)
    threshold = coverage['threshold']
    # Exported TextGrid has final geometry, not the raw MFA crop provenance.
    pauses = [{key: value for key, value in row.items()
               if key not in {'explicit_source_overlaps', 'synthetic_source_overlaps'}}
              for row in coverage['pauses']]
    suspect = sum(row['suspect'] for row in pauses)
    return {'textgrid': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'audio_sha256': hashlib.sha256(audio_path.read_bytes()).hexdigest(),
            'duration': duration, 'adjacent_pause_pairs': adjacent, 'punctuation_mismatches': mismatches,
            'structural_error': structural_error, 'energy_threshold': threshold,
            'suspect_pause_count': suspect, 'pauses': pauses,
            'passed': not (structural_error or adjacent or mismatches or suspect)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    results = []
    for path in sorted(args.directory.rglob('*.TextGrid')):
        try:
            results.append(audit(path))
        except (ValueError, OSError, RuntimeError) as exc:
            results.append({'textgrid': str(path), 'passed': False, 'error': str(exc)})
    payload = {'files': len(results), 'failed': sum(not r['passed'] for r in results), 'results': results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: payload[key] for key in ('files', 'failed')}))
    raise SystemExit(1 if payload['failed'] or not results else 0)


if __name__ == '__main__':
    main()
