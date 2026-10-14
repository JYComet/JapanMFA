import array
import json
import math
import sys
import wave
from pathlib import Path

import pytest

from tools import galgame_mfa_from_ctc as worker


def source(root, stem):
    for sub in ("wav", "txt", "ctc"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    with wave.open(str(root / "wav" / (stem + ".wav")), "wb") as w:
        w.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        w.writeframes(array.array("h", [100] * 16000).tobytes())
    (root / "txt" / (stem + ".txt")).write_text("今日", encoding="utf-8")
    from praatio import textgrid
    grid = textgrid.Textgrid()
    grid.addTier(textgrid.IntervalTier("words", [(0, 1, "今日")], 0, 1))
    grid.addTier(textgrid.PointTier("zero_duration", [], 0, 1))
    grid.save(str(root / "ctc" / (stem + ".TextGrid")), format="long_textgrid", includeBlankSpaces=True)
    return root / "wav" / (stem + ".wav")


def test_parallel_preflight_and_local_snapshots_preserve_order_and_triples(tmp_path):
    root = tmp_path / "source"
    paths = [source(root, "z"), source(root, "a"), source(root, "m")]
    expected = worker.preflight(root, paths)
    assert worker.preflight(root, paths, workers=8) == expected
    local = tmp_path / "local"
    worker.stage_sources(expected, local, workers=8)
    for row in expected:
        for field, extension in [("wav", ".wav"), ("txt", ".txt"), ("ctc", ".TextGrid")]:
            assert (local / (row["stem"] + extension)).read_bytes() == Path(row[field]).read_bytes()


def test_changed_source_is_rejected_during_snapshot(tmp_path):
    root = tmp_path / "source"; path = source(root, "one")
    rows = worker.preflight(root, [path])
    (root / "txt/one.txt").write_text("changed")
    with pytest.raises(ValueError, match="source changed"):
        worker.stage_sources(rows, tmp_path / "local", workers=8)


def test_verified_snapshot_reads_each_original_once_and_preserves_rows(tmp_path, monkeypatch):
    root = tmp_path / "source"
    paths = [source(root, "a"), source(root, "b")]
    expected = worker.preflight(root, paths)
    originals = {str(path) for folder in ("wav", "txt", "ctc")
                 for path in (root / folder).iterdir()}
    opened = {path: 0 for path in originals}
    original_open = Path.open

    def count_open(path, *args, **kwargs):
        if str(path) in opened:
            opened[str(path)] += 1
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", count_open)
    stage = tmp_path / "snapshot"
    rows = worker.snapshot_preflight(root, paths, stage, workers=2)
    assert opened == {path: 1 for path in originals}
    for actual, prior in zip(rows, expected):
        assert {key: actual[key] for key in prior} == prior
        assert actual["snapshot_wav"] == str(stage / f"{prior['stem']}.wav")
        assert Path(actual["snapshot_wav"]).read_bytes() == Path(prior["wav"]).read_bytes()


def test_verified_snapshot_rejects_source_change_without_ready_file(tmp_path, monkeypatch):
    root = tmp_path / "source"
    wav = source(root, "one")
    original_stat = Path.stat
    calls = 0

    def mutate_before_second_stat(path, *args, **kwargs):
        nonlocal calls
        if path == wav:
            calls += 1
            if calls == 2:
                with wav.open("ab") as stream:
                    stream.write(b"changed")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", mutate_before_second_stat)
    stage = tmp_path / "snapshot"
    with pytest.raises(ValueError, match="source changed"):
        worker.snapshot_preflight(root, [wav], stage)
    assert not (stage / "one.wav").exists()


def test_publish_pair_uses_verified_local_wav_without_reopening_nas(tmp_path, monkeypatch):
    root = tmp_path / "source"
    wav = source(root, "one")
    snapshot = tmp_path / "input"
    snapshot.mkdir()
    local = snapshot / "one.wav"
    local.write_bytes(wav.read_bytes())
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    (artifact / "one.wav").write_bytes(local.read_bytes())
    (artifact / "one.TextGrid").write_text("grid")
    monkeypatch.setattr(worker, "audit", lambda _path: {"passed": True})
    original_open = Path.open

    def reject_nas_open(path, *args, **kwargs):
        if path == wav:
            raise AssertionError("publication reopened NAS source")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", reject_nas_open)
    row = {"stem": "one", "wav": str(wav), "wav_sha256": worker.sha(local),
           "snapshot_wav": str(local)}
    result = worker.publish_pair(row, artifact, tmp_path / "out", tmp_path / "before")
    assert Path(result["wav"]).read_bytes() == local.read_bytes()
    assert result["wav_sha256"] == row["wav_sha256"]


def test_snapshot_stage_is_linked_to_selected_local_disk(tmp_path):
    run = tmp_path / "state/work/abc123/run"
    snapshot_root = tmp_path / "nvme"
    stage = worker.create_snapshot_stage(run, snapshot_root, min_free_bytes=0)
    assert stage.is_symlink()
    assert stage.resolve() == snapshot_root / "abc123/input"
    assert (stage / "probe").parent.resolve() == snapshot_root / "abc123/input"
    with pytest.raises(FileExistsError):
        worker.create_snapshot_stage(run, snapshot_root, min_free_bytes=0)


def test_prepare_entry_uses_nvme_snapshot_when_enabled(tmp_path, monkeypatch):
    root = tmp_path / "source"
    source(root, "one")
    run = tmp_path / "state/work/abc123/run"
    snapshots = tmp_path / "nvme"
    monkeypatch.setenv("JAPANMFA_NVME_SNAPSHOT_ROOT", str(snapshots))
    monkeypatch.setattr(worker.PipelineConfig, "load", lambda _path: (_ for _ in ()).throw(
        RuntimeError("stop after input")))
    monkeypatch.setattr(sys, "argv", [
        "galgame_mfa_from_ctc.py", str(root), "--stems", "one",
        "--alignment-strategy", "resident-timed", "--prepare-only",
        "--config", str(tmp_path / "config.yaml"), "--run-dir", str(run),
        "--output", str(tmp_path / "out")])
    with pytest.raises(RuntimeError, match="stop after input"):
        worker.main()
    assert (run / "input").resolve() == snapshots / "abc123/input"
    assert json.loads((run / "input-timings.json").read_text())["snapshot_mode"] == "single_pass_nvme"
    assert json.loads((run / "input/.snapshot-ready.json").read_text()) == {"sources": 1}


def test_prepare_missing_wav_is_rejected_without_serial_existence_probe(tmp_path, monkeypatch):
    root = tmp_path / "source"
    wav = source(root, "missing")
    wav.unlink()
    original_is_file = Path.is_file

    def reject_redundant_probe(path):
        if path == wav:
            raise AssertionError("preparation probed WAV existence before preflight")
        return original_is_file(path)

    monkeypatch.setattr(Path, "is_file", reject_redundant_probe)
    monkeypatch.setattr(sys, "argv", [
        "galgame_mfa_from_ctc.py", str(root), "--stems", "missing",
        "--alignment-strategy", "resident-timed", "--prepare-only",
        "--config", str(tmp_path / "config.yaml"),
        "--run-dir", str(tmp_path / "run"), "--output", str(tmp_path / "out"),
    ])
    with pytest.raises(ValueError, match="one or more requested WAV stems are missing"):
        worker.main()
