"""Run independent MFA corpus shards with isolated MFA model roots.

The existing CTC catalog partitions source stems once. Each shard owns a
separate resume database and MFA_ROOT_DIR, while all accepted TextGrids go to
the same game-relative output tree. Run only after stopping the serial job.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import signal
import sqlite3
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent


def shard_targets(total: int, shards: int) -> list[int]:
    if total < 1 or shards < 1:
        raise ValueError("target and shard counts must be positive")
    base, extra = divmod(total, shards)
    return [base + (index < extra) for index in range(shards)]


def remaining_items(state: Path, target: int) -> int:
    database = state / "progress.sqlite3"
    if not database.is_file():
        return target
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=30) as connection:
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='items'").fetchone():
            return target
        count = connection.execute("SELECT count(*) FROM items").fetchone()[0]
    return max(0, target - count)


@dataclass(frozen=True)
class WorkerSpec:
    command: list[str]
    environment: dict[str, str]
    log: Path


def worker_spec(index: int, manifest: Path, state: Path, config: Path,
                source: Path, output: Path, remaining: int, batch_size: int) -> WorkerSpec:
    if remaining < 1 or batch_size < 1:
        raise ValueError("worker needs a positive remaining count and batch size")
    shard_name = f"shard-{index:02d}"
    environment = os.environ.copy()
    environment["PATH"] = str(REPO / ".runtime/envs/mfa/bin") + os.pathsep + environment.get("PATH", "")
    environment["MFA_ROOT_DIR"] = str(state / "mfa-root" / shard_name)
    environment["JAPANMFA_TDMELODIC_COMMAND"] = "docker run --rm -i japanmfa-tdmelodic:e7fdb63f85bb"
    environment["PYTHONPATH"] = os.pathsep.join((str(REPO / "src"), str(REPO),
                                                 environment.get("PYTHONPATH", "")))
    command = [str(REPO / ".runtime/envs/orchestrator/bin/python"), "-u",
               str(REPO / "tools/galgame_mfa_all.py"), "--source", str(source),
               "--output", str(output), "--state", str(state / "shards" / shard_name),
               "--config", str(config), "--manifest", str(manifest),
               "--batch-size", str(batch_size), "--max-items", str(remaining)]
    return WorkerSpec(command, environment, state / "logs" / f"{shard_name}.log")


def completed_summary(log: Path, exit_code: int) -> dict[str, int] | None:
    if exit_code not in (0, 1) or not log.is_file():
        return None
    with log.open("rb") as stream:
        stream.seek(max(0, log.stat().st_size - 8192))
        lines = stream.read().decode("utf-8", errors="replace").splitlines()
    if not lines:
        return None
    try:
        result = json.loads(lines[-1])
    except (ValueError, TypeError):
        return None
    required = {"complete", "incomplete", "published", "filtered", "preflight_failed"}
    return result if isinstance(result, dict) and required <= result.keys() else None


def _atomic_json(path: Path, value: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def supervise(source: Path, output: Path, state: Path, config: Path, catalog: Path,
              *, target_items: int, workers: int, batch_size: int,
              poll_seconds: float = 30.0) -> dict[str, object]:
    if workers < 1 or batch_size < 1 or target_items < 1 or poll_seconds <= 0:
        raise ValueError("workers, batch-size, target-items and poll interval must be positive")
    manifests = sorted(catalog.glob("shard_*.jsonl"),
                       key=lambda path: int(path.stem.split("_")[-1]))
    if not manifests or [int(path.stem.split("_")[-1]) for path in manifests] != list(range(len(manifests))):
        raise ValueError("catalog needs contiguous shard_0..N JSONL manifests")
    summary_path = catalog / "catalog_summary.json"
    if not summary_path.is_file():
        raise ValueError("CTC catalog summary is missing")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if target_items > int(summary["paired"]):
        raise ValueError("target exceeds catalog WAV/TXT pair count")
    if state == source or source in state.parents or state == output or output in state.parents:
        raise ValueError("state must be separate from source and output")
    state.mkdir(parents=True, exist_ok=True)
    (state / "logs").mkdir(exist_ok=True)
    targets = shard_targets(target_items, len(manifests))
    config_sha256 = hashlib.sha256(config.read_bytes()).hexdigest()
    plan_path = state / "plan.json"
    plan = {"target_items": target_items, "catalog": str(catalog),
            "source": str(source), "output": str(output), "config": str(config),
            "config_sha256": config_sha256,
            "targets": targets}
    if plan_path.is_file():
        if json.loads(plan_path.read_text(encoding="utf-8")) != plan:
            raise ValueError("existing parallel state belongs to a different target or input plan")
    else:
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    active: dict[int, tuple[subprocess.Popen, object]] = {}
    finished: dict[int, dict[str, int]] = {}
    stopped = False
    started = time.monotonic()
    start_recorded = sum(targets[index] - remaining_items(
        state / "shards" / f"shard-{index:02d}", targets[index]) for index in range(len(manifests)))

    def stop(_signal: int, _frame: object) -> None:
        nonlocal stopped
        stopped = True

    def status(phase: str, error: str | None = None) -> dict[str, object]:
        done = [targets[index] - remaining_items(state / "shards" / f"shard-{index:02d}", targets[index])
                for index in range(len(manifests))]
        elapsed = max(0.001, time.monotonic() - started)
        total_done = sum(done)
        rate = max(0, total_done - start_recorded) / elapsed
        value: dict[str, object] = {
            "status": phase, "updated_at": time.time(), "target_items": target_items,
            "recorded_items": total_done, "items_per_second_since_start": rate,
            "eta_days_at_current_rate": None if rate <= 0 else (target_items - total_done) / rate / 86400,
            "active": {str(index): process.pid for index, (process, _) in active.items()},
            "finished": sorted(finished), "per_shard_recorded": done, "error": error,
        }
        _atomic_json(state / "status.json", value)
        return value

    serial_state = REPO / ".runtime/jobs/galgame-mfa-all"
    serial_state.mkdir(parents=True, exist_ok=True)
    with (state / "supervisor.lock").open("w") as own_lock:
        try:
            fcntl.flock(own_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("another parallel MFA supervisor is active") from exc
        # The older serial supervisor would otherwise publish the same files.
        with (serial_state / "orchestration.lock").open("a+") as serial_lock:
            try:
                fcntl.flock(serial_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("stop the active serial MFA supervisor before parallel MFA") from exc
            previous_term = signal.signal(signal.SIGTERM, stop)
            previous_int = signal.signal(signal.SIGINT, stop)
            queue = [index for index, target in enumerate(targets)
                     if remaining_items(state / "shards" / f"shard-{index:02d}", target)]
            try:
                while (queue or active) and not stopped:
                    while queue and len(active) < workers:
                        index = queue.pop(0)
                        remaining = remaining_items(state / "shards" / f"shard-{index:02d}", targets[index])
                        if not remaining:
                            continue
                        spec = worker_spec(index, manifests[index], state, config, source, output,
                                           remaining, batch_size)
                        spec.log.parent.mkdir(parents=True, exist_ok=True)
                        if spec.log.exists():
                            archived = spec.log.with_name(f"{spec.log.stem}.{uuid.uuid4().hex}.old.log")
                            spec.log.rename(archived)
                        log = spec.log.open("w", encoding="utf-8", buffering=1)
                        process = subprocess.Popen(spec.command, cwd=REPO, env=spec.environment,
                                                   stdout=log, stderr=subprocess.STDOUT,
                                                   start_new_session=True)
                        active[index] = process, log
                    status("running")
                    for index, (process, log) in list(active.items()):
                        code = process.poll()
                        if code is None:
                            continue
                        log.close()
                        del active[index]
                        result = completed_summary(state / "logs" / f"shard-{index:02d}.log", code)
                        if result is None:
                            raise RuntimeError(f"shard {index} failed without a complete summary; inspect its log")
                        finished[index] = result
                    if queue or active:
                        time.sleep(poll_seconds)
                result = status("stopped" if stopped else "complete" if sum(
                    targets[index] - remaining_items(state / "shards" / f"shard-{index:02d}", targets[index])
                    for index in range(len(manifests))) >= target_items else "waiting_for_ctc")
            except Exception as exc:
                status("attention_required", f"{type(exc).__name__}: {exc}")
                raise
            finally:
                for process, _ in active.values():
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                for process, log in active.values():
                    try:
                        process.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                    log.close()
                signal.signal(signal.SIGTERM, previous_term)
                signal.signal(signal.SIGINT, previous_int)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("/mnt/Raw/JapGalgame"))
    parser.add_argument("--output", type=Path, default=Path("/mnt/Raw/GalgameMFA"))
    parser.add_argument("--state", type=Path, default=REPO / ".runtime/jobs/galgame-mfa-parallel")
    parser.add_argument("--catalog", type=Path, default=REPO / ".runtime/jobs/japgalgame-ctc-full16-20260928")
    parser.add_argument("--config", type=Path, default=REPO / "runs/0922jap-internal-ellipsis-20260929T084752Z/final-config.yaml")
    parser.add_argument("--target-items", type=int, required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()
    source, output, state, catalog, config = (path.resolve() for path in
                                              (args.source, args.output, args.state,
                                               args.catalog, args.config))
    if not source.is_dir() or not config.is_file():
        parser.error("source and config must exist")
    result = supervise(source, output, state, config, catalog,
                       target_items=args.target_items, workers=args.workers,
                       batch_size=args.batch_size)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
