from __future__ import annotations

import json
import fcntl
import sqlite3
import sys
from pathlib import Path

import pytest

from tools import galgame_mfa_parallel as parallel


def test_target_distribution_is_exact_and_stable() -> None:
    assert parallel.shard_targets(500_000, 16) == [31_250] * 16
    assert parallel.shard_targets(11, 4) == [3, 3, 3, 2]


def test_worker_command_uses_one_manifest_and_independent_state(tmp_path: Path) -> None:
    manifest = tmp_path / "shard_3.jsonl"
    manifest.write_text("", encoding="utf-8")
    spec = parallel.worker_spec(3, manifest, tmp_path / "state", tmp_path / "config.yaml",
                                tmp_path / "source", tmp_path / "output", 120, 500)
    assert spec.command[-2:] == ["--max-items", "120"]
    assert spec.command.count("--manifest") == 1
    assert str(manifest) in spec.command
    assert spec.environment["MFA_ROOT_DIR"] == str(tmp_path / "state/mfa-root/shard-03")
    assert "--state" in spec.command
    assert str(tmp_path / "state/shards/shard-03") in spec.command


def test_resume_cap_subtracts_recorded_items(tmp_path: Path) -> None:
    shard = tmp_path / "shard"
    shard.mkdir()
    with sqlite3.connect(shard / "progress.sqlite3") as connection:
        connection.execute("CREATE TABLE items (key TEXT PRIMARY KEY, status TEXT)")
        connection.executemany("INSERT INTO items VALUES (?, ?)",
                               [("a", "passed"), ("b", "filtered")])
    assert parallel.remaining_items(shard, 3) == 1
    assert parallel.remaining_items(shard, 2) == 0


def test_completed_worker_accepts_filtered_exit_code_with_final_summary(tmp_path: Path) -> None:
    log = tmp_path / "worker.log"
    log.write_text('batch output\n' + json.dumps({"complete": 20, "incomplete": 0, "published": 18,
                  "filtered": 2, "preflight_failed": 0}) + "\n", encoding="utf-8")
    assert parallel.completed_summary(log, 1)["filtered"] == 2
    assert parallel.completed_summary(log, 2) is None


def test_parallel_supervisor_refuses_active_serial_job(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    serial = repo / ".runtime/jobs/galgame-mfa-all"
    serial.mkdir(parents=True)
    monkeypatch.setattr(parallel, "REPO", repo)
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    (catalog / "catalog_summary.json").write_text('{"paired": 10}')
    (catalog / "shard_0.jsonl").write_text("")
    (tmp_path / "config").write_text("config")
    with (serial / "orchestration.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match="stop the active serial MFA"):
            parallel.supervise(tmp_path / "source", tmp_path / "output", tmp_path / "state",
                               tmp_path / "config", catalog, target_items=1,
                               workers=1, batch_size=1)


def test_supervisor_completes_one_shard_from_worker_checkpoint(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(parallel, "REPO", repo)
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    (catalog / "catalog_summary.json").write_text('{"paired": 1}')
    (catalog / "shard_0.jsonl").write_text("")
    (tmp_path / "config").write_text("config")
    state = tmp_path / "state"
    worker_code = """import json, sqlite3, sys
from pathlib import Path
path = Path(sys.argv[1])
path.mkdir(parents=True)
with sqlite3.connect(path / 'progress.sqlite3') as db:
    db.execute('CREATE TABLE items (key TEXT PRIMARY KEY)')
    db.execute("INSERT INTO items VALUES ('sample')")
print(json.dumps(dict(complete=1, incomplete=0, published=0, filtered=1, preflight_failed=0)))
sys.exit(1)
"""
    monkeypatch.setattr(parallel, "worker_spec", lambda index, *_args: parallel.WorkerSpec(
        [sys.executable, "-c", worker_code, str(state / "shards/shard-00")],
        dict(__import__("os").environ), state / "logs/shard-00.log"))
    result = parallel.supervise(tmp_path / "source", tmp_path / "output", state,
                                tmp_path / "config", catalog, target_items=1,
                                workers=1, batch_size=1, poll_seconds=0.01)
    assert result["status"] == "complete"
    assert result["recorded_items"] == 1
