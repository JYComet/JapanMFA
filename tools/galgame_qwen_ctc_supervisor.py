"""Supervise eight resumable Qwen timestamp workers and record GPU/process health."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def assigned_gpu(shard: int, gpus: int) -> int:
    if shard < 0 or gpus < 1:
        raise ValueError('invalid shard or GPU count')
    return shard % gpus


def summarize_states(state: Path, workers: int) -> dict[str, int]:
    catalog = json.loads((state / 'catalog_summary.json').read_text(encoding='utf-8'))
    summary = {'paired': int(catalog['paired']), 'missing_txt': int(catalog['missing_txt']),
               'missing_wav': int(catalog['missing_wav']), 'success': 0, 'failed': 0,
               'seen': 0, 'workers_complete': 0}
    for index in range(workers):
        path = state / f'worker_{index}.json'
        if not path.is_file():
            continue
        worker = json.loads(path.read_text(encoding='utf-8'))
        summary['success'] += int(worker['done']) + int(worker['existing'])
        summary['failed'] += int(worker['failed'])
        summary['seen'] += int(worker['seen'])
        summary['workers_complete'] += worker['status'] == 'complete'
    summary['remaining'] = max(0, summary['paired'] - summary['seen'])
    return summary


def completion_status(summary: dict[str, int], *, workers_complete: int, workers: int) -> str:
    if workers_complete != workers or summary['remaining']:
        return 'attention_required'
    if summary['failed'] or summary['missing_txt'] or summary['missing_wav']:
        return 'complete_with_failures'
    return 'complete'


def gpu_snapshot() -> list[dict[str, str]]:
    command = ['nvidia-smi', '--query-gpu=index,memory.used,memory.free,utilization.gpu',
               '--format=csv,noheader,nounits']
    try:
        output = subprocess.run(command, capture_output=True, text=True, timeout=10, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    rows = []
    for line in output.splitlines():
        parts = [part.strip() for part in line.split(',')]
        if len(parts) == 4:
            rows.append(dict(zip(('index', 'memory_used_mib', 'memory_free_mib', 'utilization_percent'), parts)))
    return rows


def supervise(state: Path, python: Path, gpus: int, batch_size: int, model: Path,
              workers: int | None = None) -> int:
    if not (state / 'catalog_summary.json').is_file():
        raise ValueError('catalog must finish before workers start')
    workers = gpus if workers is None else workers
    catalog = json.loads((state / 'catalog_summary.json').read_text(encoding='utf-8'))
    if (gpus < 1 or workers < gpus or batch_size < 1 or not model.is_dir()
            or len(catalog['shard_counts']) != workers):
        raise ValueError('invalid GPU/worker count, batch size, or model/manifest')
    lock = (state / 'supervisor.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError('another timestamp supervisor is already running')
    lock.write(str(os.getpid()) + '\n')
    lock.flush()
    repo = Path(__file__).resolve().parent.parent
    script = repo / 'tools/galgame_qwen_ctc.py'
    children: dict[int, subprocess.Popen] = {}
    logs: dict[int, Any] = {}
    completed: set[int] = set()
    issues: dict[int, str] = {}
    restarts = {index: deque() for index in range(gpus)}
    stopping = False

    def stop(_signum: int, _frame: Any) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    def spawn(index: int) -> None:
        env = os.environ.copy()
        env['CUDA_VISIBLE_DEVICES'] = str(assigned_gpu(index, gpus))
        env['JAPANMFA_ALIGNER_MODEL_PATH'] = str(model)
        env['PYTHONPATH'] = str(repo / 'src') + os.pathsep + str(repo)
        log = (state / f'worker_{index}.log').open('a', encoding='utf-8', buffering=1)
        argv = [str(python), '-u', str(script), 'worker', '--state', str(state),
                '--shard', str(index), '--batch-size', str(batch_size)]
        child = subprocess.Popen(argv, cwd=repo, env=env, stdout=log,
                                 stderr=subprocess.STDOUT, start_new_session=True)
        children[index] = child
        logs[index] = log
        print(f'{time.ctime()}: shard {index} GPU {assigned_gpu(index, gpus)} started PID {child.pid}', flush=True)

    for index in range(workers):
        spawn(index)
    try:
        while not stopping and len(completed) < workers:
            now = time.time()
            for index, child in list(children.items()):
                returncode = child.poll()
                if returncode is None:
                    status = state / f'worker_{index}.json'
                    if status.is_file() and now - status.stat().st_mtime > 900:
                        issues[index] = 'no progress checkpoint for 15 minutes'
                        child.terminate()
                        try:
                            child.wait(timeout=30)
                        except subprocess.TimeoutExpired:
                            child.kill()
                        returncode = child.wait()
                if returncode is None:
                    continue
                logs[index].close()
                del children[index]
                if returncode == 0:
                    worker = json.loads((state / f'worker_{index}.json').read_text(encoding='utf-8'))
                    if worker['status'] == 'complete' and worker['seen'] == worker['total']:
                        completed.add(index)
                        issues.pop(index, None)
                        print(f'{time.ctime()}: shard {index} complete', flush=True)
                        continue
                    issues[index] = 'worker exited before completing its manifest'
                else:
                    issues[index] = f'worker exited {returncode}'
                recent = restarts[index]
                while recent and now - recent[0] > 3600:
                    recent.popleft()
                if len(recent) >= 3:
                    issues[index] += '; restart limit reached'
                    print(f'{time.ctime()}: shard {index} {issues[index]}', flush=True)
                    continue
                recent.append(now)
                print(f'{time.ctime()}: shard {index} {issues[index]}; restarting', flush=True)
                spawn(index)
            summary = summarize_states(state, workers)
            _atomic_json(state / 'supervisor.json', {
                'updated_at': now, 'pid': os.getpid(), 'active': {str(i): p.pid for i, p in children.items()},
                'complete': sorted(completed), 'issues': {str(k): v for k, v in issues.items()},
                'progress': summary, 'gpus': gpu_snapshot(),
                'status': 'running' if children else 'attention_required',
            })
            print(f'{time.ctime()}: progress {summary} active={sorted(children)} issues={issues}', flush=True)
            if not children and issues:
                break
            time.sleep(30)
    finally:
        for child in children.values():
            child.terminate()
        for child in children.values():
            try:
                child.wait(timeout=30)
            except subprocess.TimeoutExpired:
                child.kill()
        for log in logs.values():
            if not log.closed:
                log.close()
        summary = summarize_states(state, workers)
        final_status = 'stopped' if stopping else completion_status(summary, workers_complete=len(completed), workers=workers)
        _atomic_json(state / 'supervisor.json', {
            'updated_at': time.time(), 'pid': os.getpid(), 'active': {},
            'complete': sorted(completed), 'issues': {str(k): v for k, v in issues.items()},
            'progress': summary, 'gpus': gpu_snapshot(), 'status': final_status,
        })
    return 0 if final_status == 'complete' and not issues else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--python', type=Path, required=True)
    parser.add_argument('--gpus', type=int, default=8)
    parser.add_argument('--workers', type=int, default=None)
    parser.add_argument('--batch-size', type=int, default=8)
    parser.add_argument('--model', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(supervise(args.state.resolve(), args.python.resolve(),
                              args.gpus, args.batch_size, args.model.resolve(), args.workers))


if __name__ == '__main__':
    main()
