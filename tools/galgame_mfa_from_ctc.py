"""Run JapanMFA on a Galgame wav/txt/ctc folder and publish paired results.

Example: PYTHONPATH=src:. python tools/galgame_mfa_from_ctc.py GAME --limit 10 \
  --config runs/0922jap-internal-ellipsis-20260929T084752Z/final-config.yaml \
  --run-dir runs/galgame-akabei-first10-20260929
"""

from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import os
import shutil
import wave
from dataclasses import replace
from pathlib import Path

from japanmfa.asr.precomputed_ctc import OriginalAxisWav, PrecomputedCTCClient, read_ctc_words
from japanmfa.config import PipelineConfig
from japanmfa.mfa.g2p import MfaG2pClient, TerminalSokuonG2p
from japanmfa.pipeline import JapanMFAPipeline
from tools.audit_textgrid_pauses import audit


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def first_wavs(root: Path, limit: int) -> list[Path]:
    """Select lexically first WAVs without loading a potentially huge directory."""
    if limit < 1:
        raise ValueError('limit must be positive')
    with os.scandir(root / 'wav') as entries:
        names = heapq.nsmallest(limit, (item.name for item in entries
                                        if item.is_file(follow_symlinks=False)
                                        and item.name.lower().endswith('.wav')))
    return [root / 'wav' / name for name in names]


def preflight(root: Path, wavs: list[Path]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for wav in wavs:
        stem = wav.stem
        txt, ctc = root / 'txt' / f'{stem}.txt', root / 'ctc' / f'{stem}.TextGrid'
        if not txt.is_file() or not ctc.is_file():
            raise ValueError(f'missing TXT/CTC pair for {stem}')
        reference = txt.read_text(encoding='utf-8-sig')
        with wave.open(str(wav), 'rb') as audio:
            duration = audio.getnframes() / audio.getframerate()
            if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate(),
                    audio.getcomptype()) != (1, 2, 16000, 'NONE'):
                raise ValueError(f'noncanonical WAV: {wav}')
        lexical = read_ctc_words(ctc, reference, duration)
        rows.append({'stem': stem, 'wav': str(wav), 'txt': str(txt), 'ctc': str(ctc),
                     'wav_sha256': sha(wav), 'txt_sha256': sha(txt), 'ctc_sha256': sha(ctc),
                     'duration': duration, 'lexical_items': len(lexical),
                     'zero_duration_items': sum(item.start == item.end for item in lexical)})
    return rows


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(f'.{destination.name}.{os.getpid()}.partial')
    try:
        shutil.copy2(source, temp)
        os.replace(temp, destination)
    finally:
        temp.unlink(missing_ok=True)


def publish_pair(row: dict[str, object], artifact: Path, destination: Path,
                 snapshot: Path) -> dict[str, object]:
    stem = str(row['stem'])
    grid = artifact / f'{stem}.TextGrid'
    audio = artifact / f'{stem}.wav'
    source_wav = Path(str(row['wav']))
    if not grid.is_file() or not audio.is_file():
        raise ValueError(f'pipeline omitted TextGrid/WAV pair: {stem}')
    if sha(audio) != sha(source_wav):
        raise ValueError(f'pipeline WAV differs from original time axis: {stem}')
    local_check = audit(grid)
    if not local_check['passed']:
        raise ValueError(f'output acoustic/structural audit failed: {stem}: {local_check}')
    for path in (destination / grid.name, destination / audio.name):
        if path.exists() and sha(path) != sha(grid if path.suffix == '.TextGrid' else source_wav):
            _atomic_copy(path, snapshot / path.name)
    _atomic_copy(grid, destination / grid.name)
    _atomic_copy(source_wav, destination / audio.name)
    published_check = audit(destination / grid.name)
    if not published_check['passed']:
        raise ValueError(f'published audit failed: {stem}')
    return {'textgrid': str(destination / grid.name), 'wav': str(destination / audio.name),
            'textgrid_sha256': sha(destination / grid.name),
            'wav_sha256': sha(destination / audio.name), 'audit': published_check}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--limit', type=int, default=10)
    parser.add_argument('--stems', nargs='+', help='retry named WAV stems instead of the first N')
    parser.add_argument('--config', type=Path, default=Path('configs/default.yaml'))
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=None)
    args = parser.parse_args()
    root, run = args.root.resolve(), args.run_dir.resolve()
    if root == run or root in run.parents or run in root.parents:
        raise ValueError('run directory must be separate from source game tree')
    if args.stems:
        if len(args.stems) != len(set(args.stems)) or any(Path(stem).name != stem for stem in args.stems):
            raise ValueError('stems must be distinct plain filenames without extensions')
        wavs = [root / 'wav' / f'{stem}.wav' for stem in sorted(args.stems)]
        if not all(path.is_file() for path in wavs):
            raise ValueError('one or more requested WAV stems are missing')
    else:
        wavs = first_wavs(root, args.limit)
        if len(wavs) != args.limit:
            raise ValueError(f'found only {len(wavs)} WAVs; requested {args.limit}')
    rows = preflight(root, wavs)
    run.mkdir(parents=True, exist_ok=True)
    (run / 'preflight.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n')
    stage = run / 'input'
    stage.mkdir(exist_ok=True)
    for row in rows:
        stem = str(row['stem'])
        _atomic_copy(Path(str(row['wav'])), stage / f'{stem}.wav')
        _atomic_copy(Path(str(row['txt'])), stage / f'{stem}.txt')
    config = PipelineConfig.load(args.config)
    mfa_executable = Path(config.commands.mfa[0])
    if mfa_executable.is_absolute() and (mfa_executable.parent / 'fstcompile').is_file():
        os.environ['PATH'] = f"{mfa_executable.parent}{os.pathsep}{os.environ.get('PATH', '')}"
    config = replace(config, audio=replace(config.audio, normalize_edges=False,
                                           max_silence_sec=10000.0),
                     paths=replace(config.paths, cache_dir=run / 'cache',
                                   output_dir=run / 'pipeline'))
    adapter = PrecomputedCTCClient(
        {str(row['stem']): Path(str(row['ctc'])) for row in rows},
        {str(row['stem']): Path(str(row['txt'])).read_text(encoding='utf-8-sig') for row in rows},
    )
    pipeline = JapanMFAPipeline(
        config, audio_normalizer=OriginalAxisWav(), asr_client=adapter,
        g2p_client=TerminalSokuonG2p(MfaG2pClient(config.commands.mfa, config.mfa.g2p_model)),
    )
    batch = pipeline.run(stage, run / 'pipeline', None)
    destination = (args.output or root / 'mfa').resolve()
    report: dict[str, object] = {'source': str(root), 'output': str(destination),
                                  'run_dir': str(run), 'selected': rows, 'results': []}
    for outcome, row in zip(batch.outcomes, rows):
        result: dict[str, object] = {'stem': row['stem'], 'pipeline_status': outcome.status,
                                     'reason_code': outcome.reason_code, 'message': outcome.message}
        if outcome.status == 'aligned':
            try:
                result.update(publish_pair(row, run / 'pipeline' / str(row['stem']),
                                           destination, run / 'before'))
                result['published'] = True
            except (OSError, ValueError) as exc:
                result['published'] = False
                result['publication_error'] = str(exc)
        else:
            result['published'] = False
        report['results'].append(result)
        print(f"{row['stem']}: {outcome.status}, published={result['published']}, "
              f"reason={result.get('reason_code') or result.get('publication_error')}", flush=True)
    report['published'] = sum(item['published'] for item in report['results'])
    report['failed'] = len(rows) - report['published']
    (run / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    if destination.is_dir():
        _atomic_copy(run / 'report.json', destination / 'mfa_run_report.json')
    print(json.dumps({'selected': len(rows), 'published': report['published'],
                      'failed': report['failed'], 'report': str(run / 'report.json')},
                     ensure_ascii=False), flush=True)
    return 0 if report['failed'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
