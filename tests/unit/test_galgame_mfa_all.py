from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from tools import galgame_mfa_all as all_mfa


def _source(root: Path, game: str, relative: str, *, complete: bool = True) -> None:
    stem = Path(relative)
    for folder, extension in (("wav", ".wav"), ("txt", ".txt"), ("ctc", ".TextGrid")):
        if not complete and folder == "ctc":
            continue
        path = root / game / folder / stem.parent / f"{stem.name}{extension}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(folder.encode())


def test_catalog_only_complete_triples_preserves_game_and_relative_path(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _source(source, "Game A", "scene/line.01")
    _source(source, "Game A", "scene/missing", complete=False)
    _source(source, "Game B", "line")
    items = list(all_mfa.discover_triples(source))
    assert [(item.game, item.relative_stem.as_posix()) for item in items] == [
        ("Game A", "scene/line.01"), ("Game B", "line")]
    assert items[0].wav.name == "line.01.wav"
    assert items[0].ctc.name == "line.01.TextGrid"


def test_manifest_reader_interleaves_shards_and_skips_unfinished_ctc(tmp_path: Path) -> None:
    source = tmp_path / "source"
    for stem in ("a", "b", "c", "d"):
        _source(source, "Game", stem)
    (source / "Game/ctc/d.TextGrid").unlink()
    manifests = []
    for index, names in enumerate((("a", "b"), ("c", "d"))):
        manifest = tmp_path / f"shard_{index}.jsonl"
        with manifest.open("w", encoding="utf-8") as stream:
            for name in names:
                stream.write(json.dumps({"category": "Game", "stem": name,
                                         "wav": str(source / "Game/wav" / f"{name}.wav"),
                                         "txt": str(source / "Game/txt" / f"{name}.txt"),
                                         "ctc": str(source / "Game/ctc" / f"{name}.TextGrid")}) + "\n")
        manifests.append(manifest)
    stats: dict[str, int] = {}
    items = list(all_mfa.discover_manifest_triples(manifests, source, stats=stats))
    assert [item.relative_stem.name for item in items] == ["a", "c", "b"]
    assert stats == {"complete": 3, "incomplete": 1}


def test_only_passing_grids_are_published_and_resume_skips_unchanged(tmp_path: Path, monkeypatch) -> None:
    source, output, state = (tmp_path / name for name in ("source", "output", "state"))
    _source(source, "Game A", "scene/first")
    _source(source, "Game A", "scene/second")
    calls = []

    def fake_align(stage: Path, aliases: list[str], run: Path, destination: Path, _config: Path) -> int:
        calls.append(aliases)
        run.mkdir(parents=True)
        destination.mkdir(parents=True)
        results = []
        for index, alias in enumerate(aliases):
            passed = index == 0
            if passed:
                (destination / f"{alias}.TextGrid").write_text("accepted", encoding="utf-8")
                (destination / f"{alias}.wav").write_bytes(b"wav")
            results.append({"stem": alias, "published": passed, "chosen": "whole" if passed else None,
                            "whole_reason": None if passed else "phone_in_silence"})
        (run / "hybrid-report.json").write_text(json.dumps({"results": results}), encoding="utf-8")
        return 1

    monkeypatch.setattr(all_mfa, "audit", lambda _path: {"passed": True})
    monkeypatch.setattr(all_mfa, "preflight_source", lambda _item: None)
    summary = all_mfa.run_all(source, output, state, tmp_path / "config.yaml", batch_size=2,
                              align=fake_align)
    assert summary["published"] == 1
    assert summary["filtered"] == 1
    assert len(calls) == 1
    assert (output / "Game A/scene/first.TextGrid").read_text() == "accepted"
    assert not (output / "Game A/scene/first.wav").exists()
    assert not (output / "Game A/scene/second.TextGrid").exists()

    again = all_mfa.run_all(source, output, state, tmp_path / "config.yaml", batch_size=2,
                            align=fake_align)
    assert len(calls) == 1
    assert again["skipped_existing"] == 1
    assert again["skipped_filtered"] == 1

    all_mfa.run_all(source, output, state, tmp_path / "config.yaml", batch_size=2,
                    reprocess_all=True, align=fake_align)
    assert len(calls) == 2


def test_changed_source_reprocesses_and_removes_stale_pass(tmp_path: Path, monkeypatch) -> None:
    source, output, state = (tmp_path / name for name in ("source", "output", "state"))
    _source(source, "Game", "line")
    monkeypatch.setattr(all_mfa, "audit", lambda _path: {"passed": True})
    monkeypatch.setattr(all_mfa, "preflight_source", lambda _item: None)
    passes = iter((True, False))

    def align(_stage: Path, aliases: list[str], run: Path, destination: Path, _config: Path) -> int:
        accepted = next(passes)
        run.mkdir(parents=True)
        destination.mkdir(parents=True)
        if accepted:
            (destination / f"{aliases[0]}.TextGrid").write_text("accepted")
            (destination / f"{aliases[0]}.wav").write_bytes(b"wav")
        (run / "hybrid-report.json").write_text(json.dumps({"results": [
            {"stem": aliases[0], "published": accepted, "chosen": "whole" if accepted else None}]}))
        return 0 if accepted else 1

    all_mfa.run_all(source, output, state, tmp_path / "config.yaml", batch_size=1, align=align)
    (source / "Game/txt/line.txt").write_text("changed reference")
    all_mfa.run_all(source, output, state, tmp_path / "config.yaml", batch_size=1, align=align)
    assert not (output / "Game/line.TextGrid").exists()
    assert list((state / "obsolete").rglob("*.TextGrid"))


def test_successful_batch_removes_only_its_nvme_snapshot(tmp_path: Path, monkeypatch) -> None:
    source, output, state, snapshots = (tmp_path / name for name in
                                        ("source", "output", "state", "snapshots"))
    _source(source, "Game", "line")
    monkeypatch.setattr(all_mfa, "preflight_source", lambda _item: None)
    monkeypatch.setenv("JAPANMFA_NVME_SNAPSHOT_ROOT", str(snapshots))
    unrelated = snapshots / "other-batch/input"
    unrelated.mkdir(parents=True)
    (unrelated / "evidence").write_text("retain")

    def align(_stage: Path, aliases: list[str], run: Path,
              _destination: Path, _config: Path) -> int:
        target = snapshots / run.parent.name / "input"
        target.mkdir(parents=True)
        (target / ".snapshot-ready.json").write_text('{"sources":1}')
        run.mkdir()
        (run / "input").symlink_to(target, target_is_directory=True)
        (run / "input-timings.json").write_text(json.dumps({
            "snapshot_mode": "single_pass_nvme", "snapshot_seconds": 1.25,
            "preflight_seconds": 0.0, "sources": 1}))
        (run / "hybrid-report.json").write_text(json.dumps({"results": [
            {"stem": aliases[0], "published": False, "whole_reason": "filtered"}]}))
        return 1

    result = all_mfa.run_all(source, output, state, tmp_path / "config.yaml",
                             batch_size=1, align=align)
    assert result["filtered"] == 1
    assert (unrelated / "evidence").read_text() == "retain"
    assert sorted(path.name for path in snapshots.iterdir()) == ["other-batch"]
    archived = json.loads(next((state / "reports").glob("*.json")).read_text())
    assert archived["input_timing"]["snapshot_seconds"] == 1.25
    assert archived["input_timing"]["snapshot_mode"] == "single_pass_nvme"


def test_subprocess_reuses_worker_cache_outside_disposable_batch(tmp_path: Path, monkeypatch) -> None:
    stage = tmp_path / "state/work/batch/source"
    stage.mkdir(parents=True)
    commands = []
    monkeypatch.setattr(all_mfa.subprocess, "run", lambda command, **_kwargs: (
        commands.append(command) or SimpleNamespace(returncode=0)))
    assert all_mfa._subprocess_align(stage, ["alias"], stage.parent / "run",
                                     stage.parent / "candidate", tmp_path / "config") == 0
    command = commands[0]
    assert command[command.index("--cache-dir") + 1] == str(tmp_path / "state/cache")


def test_rejected_context_diagnostic_survives_batch_cleanup(tmp_path: Path, monkeypatch) -> None:
    source, output, state = (tmp_path / name for name in ("source", "output", "state"))
    _source(source, "Game", "line")
    monkeypatch.setattr(all_mfa, "preflight_source", lambda _item: None)

    def align(_stage, aliases, run, destination, _config):
        diagnostic = run / "pipeline-context" / aliases[0] / "postprocess.json"
        diagnostic.parent.mkdir(parents=True)
        diagnostic.write_text('{"reason":"acoustic_coverage_failed"}')
        (run / "hybrid-report.json").write_text(json.dumps({"results": [
            {"stem": aliases[0], "published": False, "whole_reason": "acoustic_coverage_failed",
             "context_retry": {"status": "postprocess_failed",
                 "postprocess": {"reason": "acoustic_coverage_failed"}}}]}))
        return 1

    summary = all_mfa.run_all(source, output, state, tmp_path / "config.yaml", batch_size=1, align=align)
    assert summary["filtered"] == 1
    assert not list((state / "work").iterdir())
    assert json.loads((state / "filtered/Game/line.context-postprocess.json").read_text()) == {
        "reason": "acoustic_coverage_failed"}
    assert not (output / "Game/line.TextGrid").exists()

    archived = json.loads(next((state / "reports").glob("*.json")).read_text())
    assert archived["report"]["results"][0]["context_retry"]["postprocess"] == {
        "reason": "acoustic_coverage_failed"}
