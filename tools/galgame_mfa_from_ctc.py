"""Run JapanMFA on a Galgame wav/txt/ctc folder and publish paired results.

Example: PYTHONPATH=src:. python tools/galgame_mfa_from_ctc.py GAME --limit 10 \
  --config runs/0922jap-internal-ellipsis-20260929T084752Z/final-config.yaml \
  --output /mnt/Raw/0922jap/GAME/mfa \
  --run-dir runs/galgame-akabei-first10-20260929
"""

from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import os
import re
import shutil
import sys
import wave
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from collections.abc import Mapping

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


def review_workers_for_run(cache_dir: Path | None, environment: Mapping[str, str]) -> int | None:
    """Lock one child to the job's review setting when it starts.

    The control file is scoped to the full-job state/work/<uuid>/cache layout;
    other callers retain the explicit environment setting or serial default.
    """
    value = environment.get('JAPANMFA_REVIEW_WORKERS')
    if value is None and cache_dir is not None:
        cache = Path(cache_dir).resolve()
        if (cache.name == 'cache' and cache.parent.parent.name == 'work'
                and re.fullmatch(r'[0-9a-f]{32}', cache.parent.name)):
            setting = cache.parents[2] / 'review-workers.txt'
            if setting.is_file():
                value = setting.read_text(encoding='utf-8').strip()
    if value is None:
        return None
    if value not in {'1', '2', '4', '8'}:
        raise ValueError('review workers must be 1, 2, 4 or 8')
    return int(value)


def resident_sockets_for_run(cache_dir: Path | None, environment: Mapping[str, str]
                             ) -> tuple[Path, Path] | None:
    """Read the live job's two-resident control only for its own work directory."""
    native = environment.get('JAPANMFA_NATIVE_SOCKET')
    if not native or cache_dir is None:
        return None
    cache = Path(cache_dir).resolve()
    if (cache.name != 'cache' or cache.parent.parent.name != 'work'
            or not re.fullmatch(r'[0-9a-f]{32}', cache.parent.name)):
        return None
    state = cache.parents[2]
    first = state / 'native-resident.sock'
    if Path(native).resolve() != first:
        return None
    control = state / 'dual-resident.enabled'
    if not control.is_file():
        return None
    if control.read_text(encoding='utf-8').strip() != '2':
        raise ValueError('invalid two-resident job control')
    second = state / 'native-resident-2.sock'
    if not first.is_socket() or not second.is_socket():
        raise ValueError('second MFA resident socket is unavailable')
    return first, second


def first_wavs(root: Path, limit: int) -> list[Path]:
    """Select lexically first WAVs without loading a potentially huge directory."""
    if limit < 1:
        raise ValueError('limit must be positive')
    with os.scandir(root / 'wav') as entries:
        names = heapq.nsmallest(limit, (item.name for item in entries
                                        if item.is_file(follow_symlinks=False)
                                        and item.name.lower().endswith('.wav')))
    return [root / 'wav' / name for name in names]


def preflight(root: Path, wavs: list[Path], *, workers: int = 1,
              flat: bool = False) -> list[dict[str, object]]:
    def inspect(wav):
        stem = wav.stem
        txt, ctc = ((root / f'{stem}.txt', root / f'{stem}.TextGrid') if flat else
                    (root / 'txt' / f'{stem}.txt', root / 'ctc' / f'{stem}.TextGrid'))
        if not txt.is_file() or not ctc.is_file():
            raise ValueError(f'missing TXT/CTC pair for {stem}')
        reference = txt.read_text(encoding='utf-8-sig')
        with wave.open(str(wav), 'rb') as audio:
            duration = audio.getnframes() / audio.getframerate()
            if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate(),
                    audio.getcomptype()) != (1, 2, 16000, 'NONE'):
                raise ValueError(f'noncanonical WAV: {wav}')
        lexical = read_ctc_words(ctc, reference, duration)
        return {'stem': stem, 'wav': str(wav), 'txt': str(txt), 'ctc': str(ctc),
                     'wav_sha256': sha(wav), 'txt_sha256': sha(txt), 'ctc_sha256': sha(ctc),
                     'duration': duration, 'lexical_items': len(lexical),
                     'zero_duration_items': sum(item.start == item.end for item in lexical)}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(inspect, wavs))


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(f'.{destination.name}.{os.getpid()}.partial')
    try:
        shutil.copy2(source, temp)
        os.replace(temp, destination)
    finally:
        temp.unlink(missing_ok=True)


def stage_sources(rows: list[dict[str, object]], stage: Path, *, workers: int = 8) -> None:
    """Copy each source triple and verify its preflight hashes before using it."""
    stage.mkdir(parents=True, exist_ok=True)
    def copy(row):
        stem = str(row['stem'])
        for field, extension in (('wav', '.wav'), ('txt', '.txt'), ('ctc', '.TextGrid')):
            target = stage / f'{stem}{extension}'
            _atomic_copy(Path(str(row[field])), target)
            if sha(target) != row[f'{field}_sha256']:
                raise ValueError(f'source changed during local snapshot: {stem}/{field}')
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(copy, rows))


def _snapshot_file(source: Path, target: Path) -> str:
    """Copy one original stream to a private local file and hash those bytes."""
    before = source.stat()
    temporary = target.with_name(f'.{target.name}.{uuid.uuid4().hex}.partial')
    digest = hashlib.sha256()
    copied = 0
    try:
        with source.open('rb') as input_stream, temporary.open('xb') as output_stream:
            for block in iter(lambda: input_stream.read(1024 * 1024), b''):
                output_stream.write(block)
                digest.update(block)
                copied += len(block)
        after = source.stat()
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns) or copied != after.st_size:
            raise ValueError(f'source changed during local snapshot: {source}')
        os.utime(temporary, ns=(before.st_atime_ns, before.st_mtime_ns))
        os.replace(temporary, target)
        return digest.hexdigest()
    finally:
        temporary.unlink(missing_ok=True)


def snapshot_preflight(root: Path, wavs: list[Path], stage: Path, *,
                       workers: int = 8) -> list[dict[str, object]]:
    """Make one verified local triple per source, then validate the local input."""
    stage.mkdir(parents=True, exist_ok=True)

    def snapshot(wav):
        stem = wav.stem
        sources = {'wav': wav, 'txt': root / 'txt' / f'{stem}.txt',
                   'ctc': root / 'ctc' / f'{stem}.TextGrid'}
        hashes = {}
        for field, extension in (('wav', '.wav'), ('txt', '.txt'), ('ctc', '.TextGrid')):
            hashes[field] = _snapshot_file(sources[field], stage / f'{stem}{extension}')
        return sources, hashes

    with ThreadPoolExecutor(max_workers=workers) as pool:
        copied = list(pool.map(snapshot, wavs))
    local = preflight(stage, [stage / f'{wav.stem}.wav' for wav in wavs],
                      workers=workers, flat=True)
    rows = []
    for local_row, (sources, hashes) in zip(local, copied):
        for field in ('wav', 'txt', 'ctc'):
            if local_row[f'{field}_sha256'] != hashes[field]:
                raise ValueError(f'local snapshot changed: {local_row["stem"]}/{field}')
            local_row[field] = str(sources[field])
        local_row['snapshot_wav'] = str(stage / f'{local_row["stem"]}.wav')
        rows.append(local_row)
    marker = stage / '.snapshot-ready.json'
    temporary = stage / f'.snapshot-ready.{uuid.uuid4().hex}.partial'
    try:
        temporary.write_text(json.dumps({'sources': len(rows)}) + '\n')
        os.replace(temporary, marker)
    finally:
        temporary.unlink(missing_ok=True)
    return rows


def create_snapshot_stage(run: Path, snapshot_root: Path, *,
                          min_free_bytes: int = 20 * 1024**3) -> Path:
    """Place this batch's flat input on the selected local volume."""
    if not snapshot_root.is_absolute():
        raise ValueError('snapshot root must be absolute')
    snapshot_root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(snapshot_root).free < min_free_bytes:
        raise OSError(f'insufficient snapshot space: {snapshot_root}')
    run.mkdir(parents=True, exist_ok=True)
    stage = run / 'input'
    if stage.exists() or stage.is_symlink():
        raise FileExistsError(f'snapshot stage already exists: {stage}')
    target = snapshot_root / run.parent.name / 'input'
    target.mkdir(parents=True, exist_ok=False)
    try:
        stage.symlink_to(target, target_is_directory=True)
    except Exception:
        target.rmdir()
        raise
    return stage


def publish_pair(row: dict[str, object], artifact: Path, destination: Path,
                 snapshot: Path) -> dict[str, object]:
    stem = str(row['stem'])
    grid = artifact / f'{stem}.TextGrid'
    audio = artifact / f'{stem}.wav'
    source_wav = Path(str(row.get('snapshot_wav') or row['wav']))
    if not grid.is_file() or not audio.is_file():
        raise ValueError(f'pipeline omitted TextGrid/WAV pair: {stem}')
    source_sha = sha(source_wav)
    if row.get('snapshot_wav') and source_sha != row['wav_sha256']:
        raise ValueError(f'local snapshot WAV changed: {stem}')
    if sha(audio) != source_sha:
        raise ValueError(f'pipeline WAV differs from original time axis: {stem}')
    local_check = audit(grid)
    if not local_check['passed']:
        raise ValueError(f'output acoustic/structural audit failed: {stem}: {local_check}')
    for path in (destination / grid.name, destination / audio.name):
        if path.exists() and sha(path) != (sha(grid) if path.suffix == '.TextGrid' else source_sha):
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
    parser.add_argument('--alignment-strategy', choices=('hybrid', 'timed', 'resident-timed'), default='hybrid',
                        help='whole-file MFA batch first, then full-WAV CTC anchor windows for failed alignments')
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--cache-dir', type=Path,
                        help='persistent local stage cache shared by successive batches of one worker')
    parser.add_argument('--output', type=Path, required=True,
                        help='destination outside the source game directory')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--use-prepared', action='store_true')
    parser.add_argument('--acoustic-groups', type=Path)
    parser.add_argument('--resident-sockets', nargs=2, type=Path)
    args = parser.parse_args()
    review_setting_source = 'environment' if 'JAPANMFA_REVIEW_WORKERS' in os.environ else 'job_control'
    selected_review_workers = review_workers_for_run(args.cache_dir, os.environ)
    if selected_review_workers is not None:
        os.environ['JAPANMFA_REVIEW_WORKERS'] = str(selected_review_workers)
        print(json.dumps({'review_workers': selected_review_workers,
                          'review_workers_source': review_setting_source}), flush=True)
    if (args.prepare_only or args.use_prepared) and args.alignment_strategy != "resident-timed":
        parser.error("prepared handoff requires resident-timed strategy")
    if args.resident_sockets and args.alignment_strategy != 'resident-timed':
        parser.error('two resident sockets require resident-timed strategy')
    resident_sockets = (args.resident_sockets if args.resident_sockets is not None else
                        resident_sockets_for_run(args.cache_dir, os.environ) if args.use_prepared else None)
    if resident_sockets is not None:
        print(json.dumps({'mfa_residents': 2, 'resident_sockets': [str(value) for value in resident_sockets]}), flush=True)
    root, run = args.root.resolve(), args.run_dir.resolve()
    if root == run or root in run.parents or run in root.parents:
        raise ValueError('run directory must be separate from source game tree')
    destination = args.output.resolve()
    if root == destination or root in destination.parents:
        raise ValueError('output directory must be outside the source game tree')
    if args.stems:
        if len(args.stems) != len(set(args.stems)) or any(Path(stem).name != stem for stem in args.stems):
            raise ValueError('stems must be distinct plain filenames without extensions')
        wavs = [root / 'wav' / f'{stem}.wav' for stem in sorted(args.stems)]
        if args.use_prepared and not all(path.is_file() for path in wavs):
            raise ValueError('one or more requested WAV stems are missing')
    else:
        wavs = first_wavs(root, args.limit)
        if len(wavs) != args.limit:
            raise ValueError(f'found only {len(wavs)} WAVs; requested {args.limit}')
    preparation = None
    if args.use_prepared:
        from japanmfa.mfa.prepared_bundle import load_prepared_bundle
        preparation, rows = load_prepared_bundle(run, sha(args.config))
        if set(str(row['stem']) for row in rows) != set(path.stem for path in wavs):
            raise ValueError("prepared source selection changed")
        stage = run / 'input'
    else:
        snapshot_root_setting = os.environ.get('JAPANMFA_NVME_SNAPSHOT_ROOT')
        snapshot_enabled = bool(snapshot_root_setting and args.alignment_strategy in {'hybrid', 'resident-timed'})
        input_started = time.monotonic()
        if snapshot_enabled:
            stage = create_snapshot_stage(run, Path(snapshot_root_setting))
            rows = snapshot_preflight(root, wavs, stage, workers=8)
            preflight_seconds = 0.0
            snapshot_seconds = time.monotonic() - input_started
        else:
            try:
                rows = preflight(root, wavs, workers=8 if args.alignment_strategy in {'hybrid', 'resident-timed'} else 1)
            except FileNotFoundError as exc:
                if args.stems and exc.filename and Path(exc.filename) in wavs:
                    raise ValueError('one or more requested WAV stems are missing') from exc
                raise
            preflight_seconds = time.monotonic() - input_started
            run.mkdir(parents=True, exist_ok=True)
            stage = run / 'input'
            stage.mkdir(exist_ok=True)
            stage_started = time.monotonic()
            if args.alignment_strategy in {'hybrid', 'resident-timed'}:
                stage_sources(rows, stage, workers=8)
            else:
                for row in rows:
                    stem = str(row['stem'])
                    _atomic_copy(Path(str(row['wav'])), stage / f'{stem}.wav')
                    _atomic_copy(Path(str(row['txt'])), stage / f'{stem}.txt')
            snapshot_seconds = time.monotonic() - stage_started
        (run / 'preflight.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n')
        (run / 'input-timings.json').write_text(json.dumps({
            'preflight_seconds': preflight_seconds,
            'snapshot_seconds': snapshot_seconds,
            'snapshot_mode': 'single_pass_nvme' if snapshot_enabled else 'legacy',
            'sources': len(rows), 'workers': 8 if args.alignment_strategy in {'hybrid', 'resident-timed'} else 1,
        }, indent=2) + '\n')
    config = PipelineConfig.load(args.config)
    native_socket = os.environ.get('JAPANMFA_NATIVE_SOCKET')
    if native_socket:
        command = (str(Path(sys.executable)), str(Path(__file__).parents[1] / 'src/japanmfa/mfa/native_resident.py'), 'call', native_socket)
        config = replace(config, commands=replace(config.commands, mfa=command))
    mfa_executable = Path(config.commands.mfa[0])
    if mfa_executable.is_absolute() and (mfa_executable.parent / 'fstcompile').is_file():
        os.environ['PATH'] = f"{mfa_executable.parent}{os.pathsep}{os.environ.get('PATH', '')}"
    config = replace(config, audio=replace(config.audio, normalize_edges=False,
                                           max_silence_sec=10000.0),
                     paths=replace(config.paths, cache_dir=(args.cache_dir or run / 'cache').resolve(),
                                   output_dir=run / 'pipeline'))
    adapter = PrecomputedCTCClient(
        {str(row['stem']): (stage / (str(row['stem']) + '.TextGrid') if args.alignment_strategy in {'hybrid', 'resident-timed'} else Path(str(row['ctc']))) for row in rows},
        {str(row['stem']): (stage / (str(row['stem']) + '.txt')).read_text(encoding='utf-8-sig') for row in rows},
    )
    if args.prepare_only:
        from tools.galgame_mfa_hybrid import _pipeline
        from japanmfa.mfa.prepared_bundle import save_prepared_bundle
        begin = time.monotonic()
        preparation = _pipeline(config, adapter, mode="timed").prepare_mfa_inputs(stage, run / "prepared", None)
        save_prepared_bundle(run, preparation, rows, sha(args.config))
        (run / "preparation-timing.json").write_text(json.dumps({"seconds": time.monotonic()-begin,
                  "prepared": len(preparation.items), "failed": len(preparation.failures), "sources": len(rows)}))
        return 0
    if args.alignment_strategy in {'hybrid', 'resident-timed'}:
        from tools.galgame_mfa_hybrid import run_hybrid, run_timed_batch
        execute = run_timed_batch if args.alignment_strategy == "resident-timed" else run_hybrid
        options = ({"preparation": preparation, "acoustic_groups": json.loads(args.acoustic_groups.read_text())
                    if args.acoustic_groups else None,
                    "resident_sockets": resident_sockets}
                   if args.alignment_strategy == "resident-timed" else {})
        report = execute(stage, rows, run, destination, config, adapter, publish_pair, sha, **options)
        if args.use_prepared:
            timing = json.loads((run / "preparation-timing.json").read_text())
            report["preparation_handoff"] = timing
            report["phase_seconds"]["preparation"] = timing["seconds"]
            report["elapsed_after_preparation_seconds"] = report["total_seconds"]
            report["total_seconds"] += timing["seconds"]
            (run / "hybrid-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n")
        destination.mkdir(parents=True, exist_ok=True)
        _atomic_copy(run / 'hybrid-report.json', destination / 'hybrid_run_report.json')
        print(json.dumps({
            'selected': len(rows), 'published_or_retained': report['published_or_retained'],
            'newly_published': report['newly_published'], 'mfa_batches': report['mfa_batches'],
            'report': str(run / 'hybrid-report.json'),
        }, ensure_ascii=False), flush=True)
        return 0 if report['published_or_retained'] == len(rows) else 1
    pipeline = JapanMFAPipeline(
        config, audio_normalizer=OriginalAxisWav(), asr_client=adapter,
        g2p_client=TerminalSokuonG2p(MfaG2pClient(config.commands.mfa, config.mfa.g2p_model)),
    )
    batch = pipeline.run(stage, run / 'pipeline', None)
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
