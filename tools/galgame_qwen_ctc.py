"""Catalog Galgame WAV/TXT pairs and produce Qwen word-time TextGrids per GPU shard."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import sys
import time
import wave
from pathlib import Path
from typing import Any, Iterable


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def _files_below(root: Path, suffix: str) -> dict[Path, Path]:
    if not root.is_dir():
        return {}
    found: dict[Path, Path] = {}
    for current, dirs, files in os.walk(root):
        dirs.sort()
        directory = Path(current)
        for name in files:
            if Path(name).suffix.lower() == suffix:
                relative = (directory / name).relative_to(root)
                stem = relative.with_suffix('')
                if stem in found:
                    raise ValueError(f'duplicate source stem in {root}: {stem}')
                found[stem] = relative
    return found


def _shard(category: str, stem: Path, shards: int) -> int:
    key = f'{category}/{stem.as_posix()}'.encode('utf-8')
    return int.from_bytes(hashlib.blake2b(key, digest_size=8).digest(), 'big') % shards


def _ctc_name(stem: Path) -> str:
    return f'{stem.name}.TextGrid'


def catalog(source: Path, state: Path, *, shards: int = 8) -> dict[str, Any]:
    """Write a stable, local manifest; never create directories in the source."""
    if shards < 1 or not source.is_dir():
        raise ValueError('source must be a directory and shards must be positive')
    if state.exists() and any(state.iterdir()):
        raise ValueError('state directory must be new or empty')
    state.mkdir(parents=True, exist_ok=True)
    streams = [(state / f'shard_{index}.jsonl').open('w', encoding='utf-8') for index in range(shards)]
    counts = {'categories': 0, 'wav': 0, 'txt': 0, 'paired': 0,
              'missing_txt': 0, 'missing_wav': 0, 'shard_counts': [0] * shards}
    errors = (state / 'catalog_errors.jsonl').open('w', encoding='utf-8')
    try:
        categories = sorted((path for path in source.iterdir() if path.is_dir()), key=lambda p: p.name)
        for category in categories:
            wavs = _files_below(category / 'wav', '.wav')
            texts = _files_below(category / 'txt', '.txt')
            if not wavs and not texts:
                continue
            counts['categories'] += 1
            counts['wav'] += len(wavs)
            counts['txt'] += len(texts)
            wav_stems, text_stems = set(wavs), set(texts)
            counts['missing_txt'] += len(wav_stems - text_stems)
            counts['missing_wav'] += len(text_stems - wav_stems)
            for stem in sorted(wav_stems - text_stems):
                errors.write(json.dumps({'category': category.name, 'stem': stem.as_posix(),
                                         'reason': 'missing_txt'}, ensure_ascii=False) + '\n')
            for stem in sorted(text_stems - wav_stems):
                errors.write(json.dumps({'category': category.name, 'stem': stem.as_posix(),
                                         'reason': 'missing_wav'}, ensure_ascii=False) + '\n')
            for stem in sorted(wav_stems & text_stems):
                shard = _shard(category.name, stem, shards)
                row = {'category': category.name, 'stem': stem.as_posix(),
                       'wav': str(category / 'wav' / wavs[stem]),
                       'txt': str(category / 'txt' / texts[stem]),
                       'ctc': str(category / 'ctc' / stem.parent / _ctc_name(stem))}
                streams[shard].write(json.dumps(row, ensure_ascii=False) + '\n')
                counts['paired'] += 1
                counts['shard_counts'][shard] += 1
            print(f"cataloged {category.name}: wav={len(wavs)} txt={len(texts)} paired={len(wav_stems & text_stems)} total={counts['paired']}", flush=True)
    finally:
        for stream in streams:
            stream.close()
        errors.close()
    _atomic_json(state / 'catalog_summary.json', counts)
    return counts


def reshard(source: Path, state: Path, *, shards: int) -> dict[str, Any]:
    """Split a completed local catalog into more independent GPU workers."""
    if not (source / 'catalog_summary.json').is_file() or shards < 1:
        raise ValueError('source catalog must be complete and shards positive')
    original = json.loads((source / 'catalog_summary.json').read_text(encoding='utf-8'))
    source_shards = len(original['shard_counts'])
    if not source_shards or shards % source_shards:
        raise ValueError('new shard count must be a multiple of source shards')
    if state.exists() and any(state.iterdir()):
        raise ValueError('state directory must be new or empty')
    state.mkdir(parents=True, exist_ok=True)
    factor = shards // source_shards
    counts = [0] * shards
    repaired_ctc_paths = 0
    dotted_stem = re.compile(rb'"stem": "[^"]*\.')
    streams = [(state / f'shard_{index}.jsonl').open('wb') for index in range(shards)]
    try:
        for old_index, expected in enumerate(original['shard_counts']):
            seen = 0
            with (source / f'shard_{old_index}.jsonl').open('rb') as inp:
                for line in inp:
                    if not line.endswith(b'\n'):
                        raise ValueError(f'incomplete catalog line in shard {old_index}')
                    if dotted_stem.search(line):
                        row = json.loads(line)
                        corrected = str(Path(row['ctc']).with_name(_ctc_name(Path(row['stem']))))
                        if row['ctc'] != corrected:
                            row['ctc'] = corrected
                            line = (json.dumps(row, ensure_ascii=False) + '\n').encode('utf-8')
                            repaired_ctc_paths += 1
                    target_index = old_index * factor + seen % factor
                    streams[target_index].write(line)
                    counts[target_index] += 1
                    seen += 1
            if seen != expected:
                raise ValueError(f'catalog count mismatch in shard {old_index}: {seen} != {expected}')
    finally:
        for stream in streams:
            stream.close()
    if sum(counts) != original['paired']:
        raise ValueError('resharded pair count does not match source catalog')
    errors = source / 'catalog_errors.jsonl'
    if errors.is_file():
        shutil.copyfile(errors, state / 'catalog_errors.jsonl')
    summary = {**original, 'shard_counts': counts, 'resharded_from': str(source),
               'repaired_ctc_paths': repaired_ctc_paths}
    _atomic_json(state / 'catalog_summary.json', summary)
    return summary


def _quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def render_textgrid(duration: float, words: list[dict[str, Any]]) -> str:
    """Represent Qwen word spans and zero-width evidence without inventing duration."""
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('invalid audio duration')
    intervals: list[tuple[float, float, str]] = []
    points: list[tuple[float, str]] = []
    cursor = 0.0
    max_boundary = 0.0
    for item in words:
        label = str(item['text'])
        start, end = float(item['start']), float(item['end'])
        if not label or not math.isfinite(start) or not math.isfinite(end) or start < 0 or end < start:
            raise ValueError('invalid Qwen word interval')
        if end > duration + 0.000001:
            raise ValueError(
                f'Qwen word exceeds audio duration: text={label!r} '
                f'end={end:.6f} duration={duration:.6f}'
            )
        if start < cursor - 0.000001:
            raise ValueError('Qwen words overlap')
        max_boundary = max(max_boundary, end)
        if start == end:
            points.append((start, label))
            continue
        if start > cursor:
            intervals.append((cursor, start, ''))
        intervals.append((start, end, label))
        cursor = end
    grid_duration = math.ceil(max(duration, max_boundary) * 1_000_000 - 1e-9) / 1_000_000
    if round(cursor, 6) < grid_duration:
        intervals.append((cursor, grid_duration, ''))
    if not intervals:
        intervals.append((0.0, grid_duration, ''))
    lines = [
        'File type = "ooTextFile"', 'Object class = "TextGrid"', '',
        'xmin = 0', f'xmax = {grid_duration:.6f}', 'tiers? <exists>', 'size = 2', 'item []:',
        '    item [1]:', '        class = "IntervalTier"', '        name = "words"',
        '        xmin = 0', f'        xmax = {grid_duration:.6f}',
        f'        intervals: size = {len(intervals)}',
    ]
    for index, (start, end, label) in enumerate(intervals, 1):
        lines.extend((f'        intervals [{index}]:', f'            xmin = {start:.6f}',
                      f'            xmax = {end:.6f}', f'            text = {_quote(label)}'))
    lines.extend(('    item [2]:', '        class = "TextTier"', '        name = "zero_duration"',
                  '        xmin = 0', f'        xmax = {grid_duration:.6f}',
                  f'        points: size = {len(points)}'))
    for index, (at, label) in enumerate(points, 1):
        lines.extend((f'        points [{index}]:', f'            number = {at:.6f}',
                      f'            mark = {_quote(label)}'))
    return '\n'.join(lines) + '\n'


def lexical_words(text: str, result: Any) -> list[dict[str, Any]]:
    """Keep Qwen lexical items; TXT retains punctuation-only model units."""
    from japanmfa.asr.timestamps import project_timestamps

    words, _punctuation = project_timestamps(text, result)
    return words


def atomic_publish_textgrid(output: Path, value: str) -> None:
    """Publish once without a redundant SMB unlink after successful rename."""
    temporary = output.with_name(f'.{output.name}.{os.getpid()}.tmp')
    published = False
    try:
        temporary.write_text(value, encoding='utf-8')
        os.replace(temporary, output)
        published = True
    finally:
        if not published:
            temporary.unlink(missing_ok=True)


def _wav_duration(path: Path) -> float:
    with wave.open(str(path), 'rb') as stream:
        if stream.getframerate() <= 0 or stream.getnframes() <= 0:
            raise ValueError('invalid or empty WAV')
        return stream.getnframes() / stream.getframerate()


def _model_align(model: Any, items: list[tuple[dict[str, str], str, float]]) -> list[Any]:
    return model.align(audio=[row['wav'] for row, _, _ in items],
                       text=[text for _, text, _ in items],
                       language=['Japanese'] * len(items))


def run_worker(state: Path, shard: int, batch_size: int) -> dict[str, Any]:
    """Resume one stable shard; a failed item cannot abort its siblings."""
    from japanmfa.asr.timestamps import clean_asr_text
    from japanmfa.asr.worker import _load_aligner

    if batch_size < 1:
        raise ValueError('batch_size must be positive')
    manifest = state / f'shard_{shard}.jsonl'
    if not manifest.is_file():
        raise ValueError(f'missing manifest: {manifest}')
    expected = json.loads((state / 'catalog_summary.json').read_text(encoding='utf-8'))['shard_counts'][shard]
    counts: dict[str, Any] = {'shard': shard, 'total': expected, 'done': 0,
                              'existing': 0, 'failed': 0, 'seen': 0, 'status': 'starting',
                              'pid': os.getpid(), 'updated_at': time.time(), 'last_item': ''}
    state_file = state / f'worker_{shard}.json'
    errors = state / f'worker_{shard}_errors.jsonl'
    model = None
    pending: list[tuple[dict[str, str], str, float]] = []
    current_ctc_dir: Path | None = None
    existing_names: set[str] = set()
    prepared_dirs: set[Path] = set()

    def already_published(output: Path) -> bool:
        nonlocal current_ctc_dir, existing_names
        if output.parent != current_ctc_dir:
            current_ctc_dir = output.parent
            existing_names = {entry.name for entry in os.scandir(current_ctc_dir)} if current_ctc_dir.is_dir() else set()
        return output.name in existing_names

    def checkpoint(status: str) -> None:
        counts['status'] = status
        counts['updated_at'] = time.time()
        _atomic_json(state_file, counts)

    def fail(row: dict[str, str], exc: Exception) -> None:
        counts['failed'] += 1
        with errors.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'category': row['category'], 'stem': row['stem'],
                                     'reason': type(exc).__name__, 'message': str(exc)[:1000]},
                                    ensure_ascii=False) + '\n')

    def publish(row: dict[str, str], value: str) -> None:
        output = Path(row['ctc'])
        if already_published(output):
            counts['existing'] += 1
            return
        if output.parent not in prepared_dirs:
            if output.parent.is_symlink():
                raise ValueError('ctc output directory is a symlink')
            output.parent.mkdir(parents=True, exist_ok=True)
            prepared_dirs.add(output.parent)
        atomic_publish_textgrid(output, value)
        existing_names.add(output.name)
        counts['done'] += 1

    def process(items: list[tuple[dict[str, str], str, float]]) -> None:
        if not items:
            return
        try:
            results = _model_align(model, items)
            if len(results) != len(items):
                raise ValueError('Qwen result count does not match batch')
        except Exception as exc:
            if len(items) == 1:
                fail(items[0][0], exc)
                return
            try:
                import torch
                torch.cuda.empty_cache()
            except Exception:
                pass
            middle = len(items) // 2
            process(items[:middle])
            process(items[middle:])
            return
        for (row, text, duration), result in zip(items, results):
            try:
                publish(row, render_textgrid(duration, lexical_words(text, result)))
            except Exception as exc:
                fail(row, exc)

    def flush() -> None:
        nonlocal model
        if not pending:
            return
        if model is None:
            model = _load_aligner('Qwen/Qwen3-ForcedAligner-0.6B')
        process(pending)
        pending.clear()
        checkpoint('running')

    checkpoint('starting')
    with manifest.open('r', encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            counts['seen'] += 1
            counts['last_item'] = f"{row['category']}/{row['stem']}"
            output = Path(row['ctc'])
            if already_published(output):
                counts['existing'] += 1
                if counts['seen'] % 100 == 0:
                    checkpoint('running')
                continue
            try:
                raw_text = Path(row['txt']).read_text(encoding='utf-8-sig')
                text = clean_asr_text(raw_text)
                if not text:
                    raise ValueError('TXT contains no lexical Japanese text')
                duration = _wav_duration(Path(row['wav']))
                pending.append((row, text, duration))
            except Exception as exc:
                fail(row, exc)
            if len(pending) >= batch_size:
                flush()
            elif counts['seen'] % 100 == 0:
                checkpoint('running')
    flush()
    checkpoint('complete')
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='command', required=True)
    scan = subparsers.add_parser('catalog')
    scan.add_argument('--source', type=Path, required=True)
    scan.add_argument('--state', type=Path, required=True)
    scan.add_argument('--shards', type=int, default=8)
    split = subparsers.add_parser('reshard')
    split.add_argument('--source-state', type=Path, required=True)
    split.add_argument('--state', type=Path, required=True)
    split.add_argument('--shards', type=int, required=True)
    worker = subparsers.add_parser('worker')
    worker.add_argument('--state', type=Path, required=True)
    worker.add_argument('--shard', type=int, required=True)
    worker.add_argument('--batch-size', type=int, default=8)
    args = parser.parse_args()
    if args.command == 'catalog':
        print(json.dumps(catalog(args.source, args.state, shards=args.shards), ensure_ascii=False))
    elif args.command == 'reshard':
        print(json.dumps(reshard(args.source_state, args.state, shards=args.shards), ensure_ascii=False))
    else:
        print(json.dumps(run_worker(args.state, args.shard, args.batch_size), ensure_ascii=False))


if __name__ == '__main__':
    main()
