"""Own the second MFA resident for one running Galgame scanner launcher."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path


def atomic_write(path: Path, value: str) -> None:
    temporary = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    temporary.write_text(value, encoding='utf-8')
    os.replace(temporary, path)


def process_start_ticks(pid: int) -> str | None:
    try:
        # Field 22 is the start time; isolate it from the parenthesized command.
        return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def summarize_report(path: Path) -> dict[str, object]:
    archive = json.loads(path.read_text(encoding='utf-8'))
    report = archive['report']
    phases = report['phase_seconds']
    return {'batch_id': path.stem, 'at': time.time(),
            'resident_count': report.get('resident_count', 1),
            'source_count': report['source_count'],
            'prepared_count': report['prepared_count'],
            'published': report['published_or_retained'],
            'mfa_align_seconds': phases['mfa_align'],
            'mfa_service_seconds': phases.get('mfa_align_service_sum'),
            'review_seconds': phases['timed_review'],
            'publication_seconds': phases['publication'],
            'total_seconds': report['total_seconds'],
            'timed_files': report['mfa_batches']['timed']['files'],
            'context_files': report['mfa_batches']['context_retry']['files']}


def run() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--parent-pid', type=int, required=True)
    parser.add_argument('--model-source', type=Path, required=True)
    parser.add_argument('--model-root', type=Path, required=True)
    args = parser.parse_args()
    state = args.state.resolve()
    model_root = args.model_root.resolve()
    first = state / 'native-resident.sock'
    second = state / 'native-resident-2.sock'
    control = state / 'dual-resident.enabled'
    status = state / 'dual-resident-status.json'
    repository = Path(__file__).resolve().parents[1]
    resident_script = repository / 'src/japanmfa/mfa/native_resident.py'
    mfa_python = repository / '.runtime/envs/mfa/bin/python'
    call_python = repository / '.runtime/envs/orchestrator/bin/python'
    parent_ticks = process_start_ticks(args.parent_pid)
    if parent_ticks is None or not first.is_socket() or second.exists() or control.exists():
        raise RuntimeError('parent, primary resident, or previous dual-resident state is invalid')
    if not args.model_source.is_dir():
        raise ValueError('private model source is missing')
    shutil.copytree(args.model_source.resolve(), model_root / 'pretrained_models', dirs_exist_ok=True)
    environment = os.environ.copy()
    environment.update(MFA_ROOT_DIR=str(model_root),
                       PYTHONPATH=f"{repository / 'src'}:{repository}",
                       PATH=f"{mfa_python.parent}{os.pathsep}{environment.get('PATH', '')}")
    stopping = False

    def stop_signal(_number, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop_signal)
    signal.signal(signal.SIGINT, stop_signal)
    service = None
    enabled = False
    error = None
    reports = state / 'reports'
    previous_report = max(reports.glob('*.json'), key=lambda path: path.stat().st_mtime_ns,
                          default=None)
    previous_report_name = None if previous_report is None else previous_report.name
    last_batch = None
    observed_batches = 0
    try:
        with (state / 'native-resident-2.log').open('a', encoding='utf-8') as log:
            service = subprocess.Popen([str(mfa_python), '-u', str(resident_script), 'serve',
                                        str(second), str(state), 'all'],
                                       cwd=repository, env=environment,
                                       stdout=log, stderr=subprocess.STDOUT)
            for _ in range(150):
                if second.is_socket():
                    break
                if service.poll() is not None or process_start_ticks(args.parent_pid) != parent_ticks:
                    raise RuntimeError('second resident or launcher stopped during startup')
                time.sleep(0.2)
            if not second.is_socket() or service.poll() is not None:
                raise RuntimeError('second resident did not become ready')
            atomic_write(control, '2\n')
            enabled = True
            while not stopping and service.poll() is None and process_start_ticks(args.parent_pid) == parent_ticks:
                latest_report = max(reports.glob('*.json'), key=lambda path: path.stat().st_mtime_ns,
                                    default=None)
                if latest_report is not None and latest_report.name != previous_report_name:
                    try:
                        summary = summarize_report(latest_report)
                    except (OSError, ValueError, KeyError):
                        pass  # The scanner may still be writing this report.
                    else:
                        with (state / 'dual-resident-batches.jsonl').open('a', encoding='utf-8') as stream:
                            stream.write(json.dumps(summary, ensure_ascii=False) + '\n')
                        previous_report_name = latest_report.name
                        last_batch = summary
                        observed_batches += 1
                native = state / 'native-resident-2.sock.status.json'
                try:
                    latest = json.loads(native.read_text()) if native.is_file() else {}
                except (OSError, ValueError):
                    latest = {}
                atomic_write(status, json.dumps({
                    'at': time.time(), 'status': 'running', 'parent_pid': args.parent_pid,
                    'service_pid': service.pid, 'socket': str(second),
                    'native_operation': latest.get('operation'),
                    'native_seconds': latest.get('seconds'),
                    'model_loads': latest.get('model_loads'),
                    'model_hits': latest.get('model_hits'),
                    'observed_batches': observed_batches,
                    'last_batch': last_batch,
                }) + '\n')
                time.sleep(5)
            if service.poll() is not None and not stopping:
                error = f'second resident exited {service.returncode}'
    except Exception as exc:
        error = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        if enabled and control.is_file():
            control.unlink()
        if service is not None:
            if service.poll() is None and second.is_socket():
                try:
                    subprocess.run([str(call_python), str(resident_script), 'stop', str(second)],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   timeout=10, check=False)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            try:
                service.wait(timeout=10)
            except subprocess.TimeoutExpired:
                service.terminate()
                service.wait(timeout=10)
        atomic_write(status, json.dumps({
            'at': time.time(), 'status': 'stopped' if error is None else 'attention_required',
            'parent_pid': args.parent_pid,
            'service_pid': None if service is None else service.pid, 'error': error,
        }) + '\n')


if __name__ == '__main__':
    run()
