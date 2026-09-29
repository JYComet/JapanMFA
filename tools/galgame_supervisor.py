"""Keep one resumable Galgame export worker on each selected GPU."""

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


def atomic_json(path: Path, value: dict) -> None:
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--gpus", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--edge-seconds", type=float, default=0.5)
    args = parser.parse_args()
    if args.gpus < 1 or args.batch_size < 1:
        parser.error("gpus and batch-size must be positive")
    source = args.input.resolve(strict=True)
    output = args.output.resolve(strict=True)
    args.state.mkdir(parents=True, exist_ok=True)
    lock = (args.state / "supervisor.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("another Galgame supervisor is already running")
    lock.write(str(os.getpid()) + "\n")
    lock.flush()
    repo = Path(__file__).resolve().parent.parent
    script = repo / "tools" / "galgame_export.py"
    children: dict[int, subprocess.Popen] = {}
    logs = {}
    completed: set[int] = set()
    restart_times = {index: deque() for index in range(args.gpus)}
    issues: dict[int, str] = {}
    stopping = False

    def handle_stop(_signal: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)

    def spawn(index: int) -> None:
        env = os.environ.copy()
        env["CUDA_VISIBLE_DEVICES"] = str(index)
        env["PYTHONPATH"] = str(repo / "src") + os.pathsep + env.get("PYTHONPATH", "")
        log = (args.state / f"worker_{index}.log").open("a", buffering=1)
        argv = [str(args.python), "-u", str(script), "--input", str(source),
                "--output", str(output), "--state", str(args.state),
                "--shard", str(index), "--shards", str(args.gpus),
                "--batch-size", str(args.batch_size), "--edge-seconds", str(args.edge_seconds)]
        children[index] = subprocess.Popen(argv, cwd=repo, env=env, stdout=log,
                                           stderr=subprocess.STDOUT, start_new_session=True)
        logs[index] = log
        print(f"{time.ctime()} started shard {index}, pid {children[index].pid}", flush=True)

    for index in range(args.gpus):
        spawn(index)
    last_audit = 0.0
    try:
        while not stopping and len(completed) < args.gpus:
            now = time.time()
            for index, child in list(children.items()):
                returncode = child.poll()
                if returncode is None:
                    state_file = args.state / f"worker_{index}.json"
                    if state_file.exists() and now - state_file.stat().st_mtime > 3600:
                        issues[index] = "no progress checkpoint for over one hour; restarting"
                        print(f"{time.ctime()} shard {index}: {issues[index]}", flush=True)
                        child.terminate()
                        try:
                            child.wait(timeout=15)
                        except subprocess.TimeoutExpired:
                            child.kill()
                        returncode = child.wait()
                if returncode is None:
                    continue
                logs[index].close()
                del children[index]
                if returncode == 0:
                    completed.add(index)
                    issues.pop(index, None)
                    print(f"{time.ctime()} shard {index} completed", flush=True)
                    continue
                recent = restart_times[index]
                while recent and now - recent[0] > 3600:
                    recent.popleft()
                if len(recent) >= 3:
                    issues[index] = f"exit {returncode}; restart limit 3/hour reached"
                    print(f"{time.ctime()} shard {index}: {issues[index]}", flush=True)
                    continue
                recent.append(now)
                issues[index] = f"exit {returncode}; restarting"
                print(f"{time.ctime()} shard {index}: {issues[index]}", flush=True)
                spawn(index)
            if now - last_audit >= 3600 or last_audit == 0:
                last_audit = now
                print(f"{time.ctime()} hourly audit: active={sorted(children)} "
                      f"complete={sorted(completed)} issues={issues}", flush=True)
            atomic_json(args.state / "supervisor.json", {
                "updated_at": now, "pid": os.getpid(), "active": {str(i): p.pid for i, p in children.items()},
                "complete": sorted(completed), "issues": issues, "hourly_audit_at": last_audit,
            })
            if not children and issues:
                break
            time.sleep(60)
    finally:
        for child in children.values():
            child.terminate()
        for child in children.values():
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill()
        for log in logs.values():
            if not log.closed:
                log.close()
        atomic_json(args.state / "supervisor.json", {
            "updated_at": time.time(), "pid": os.getpid(), "active": {},
            "complete": sorted(completed), "issues": issues,
            "status": "stopped" if stopping else "complete" if len(completed) == args.gpus else "attention_required",
        })
    if issues:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
