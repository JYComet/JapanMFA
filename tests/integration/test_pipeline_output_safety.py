from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from japanmfa.config import PathConfig
from japanmfa.pipeline import JapanMFAPipeline

from test_pipeline_fake_backends import _pipeline, _write_audio


def test_run_rejects_symlinked_intermediate_output_directory(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    _write_audio(corpus / "speaker", "clip")
    output = tmp_path / "output"
    output.mkdir()
    (output / "speaker").symlink_to(corpus, target_is_directory=True)

    with pytest.raises(ValueError, match="symlink"):
        _pipeline().run(corpus, output, None)

    assert (corpus / "speaker" / "clip.wav").is_file()
    assert not (corpus / "speaker" / "clip.TextGrid").exists()


def test_run_rejects_output_root_that_contains_input_root(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    _write_audio(corpus, "clip")

    with pytest.raises(ValueError, match="overlap"):
        _pipeline().run(corpus, tmp_path, None)


@pytest.mark.parametrize("cache_location", ["inside_input", "input_inside_cache"])
def test_run_rejects_cache_root_that_overlaps_input_before_writing(
    tmp_path: Path, cache_location: str
) -> None:
    corpus = tmp_path / "corpus"
    _write_audio(corpus, "clip")
    output = tmp_path / "output"
    cache = corpus / ".cache" if cache_location == "inside_input" else tmp_path
    pipeline = _pipeline()
    pipeline.config = replace(
        pipeline.config,
        paths=PathConfig(cache_dir=cache, output_dir=output),
    )

    with pytest.raises(ValueError, match="cache root must not overlap input root"):
        pipeline.run(corpus, output, None)

    assert not output.exists()
    assert not (corpus / ".cache").exists()


def test_run_rejects_cache_root_that_overlaps_output_before_writing(
    tmp_path: Path,
) -> None:
    corpus = tmp_path / "corpus"
    _write_audio(corpus, "clip")
    output = tmp_path / "output"
    pipeline = _pipeline()
    pipeline.config = replace(
        pipeline.config,
        paths=PathConfig(cache_dir=output / ".cache", output_dir=output),
    )

    with pytest.raises(ValueError, match="cache root must not overlap output root"):
        pipeline.run(corpus, output, None)

    assert not output.exists()


def test_alignment_output_failure_removes_both_published_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus = tmp_path / "corpus"
    _write_audio(corpus, "clip")
    output = tmp_path / "output"
    pipeline = _pipeline()
    pipeline.config = replace(
        pipeline.config,
        paths=PathConfig(cache_dir=tmp_path / "cache", output_dir=output),
    )
    assert pipeline.run(corpus, output, None).outcomes[0].status == "aligned"
    artifact = output / "clip"
    assert (artifact / "clip.TextGrid").is_file()
    assert (artifact / "alignment.json").is_file()
    assert (artifact / ".japanmfa.complete").is_file()

    original_write_json = __import__("japanmfa.pipeline", fromlist=["write_json"]).write_json

    def fail_alignment(path: Path, payload: object) -> None:
        if path.name == "alignment.json":
            raise OSError("injected alignment write failure")
        original_write_json(path, payload)

    monkeypatch.setattr("japanmfa.pipeline.write_json", fail_alignment)
    result = pipeline.run(corpus, output, None)

    assert result.outcomes[0].status == "failed"
    assert not (artifact / "clip.TextGrid").exists()
    assert not (artifact / "alignment.json").exists()
    assert not (artifact / ".japanmfa.complete").exists()


def test_stale_final_cleanup_failure_is_a_typed_item_failure(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    _write_audio(corpus, "clip")
    output = tmp_path / "output"
    stale_grid = output / "clip" / "clip.TextGrid"
    stale_grid.mkdir(parents=True)

    result = _pipeline().run(corpus, output, None)

    assert result.outcomes[0].status == "failed"
    assert result.outcomes[0].reason_code == "final_cleanup_failed"
    assert stale_grid.is_dir()


def test_success_then_early_failure_does_not_leave_stale_final_outputs(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    _write_audio(corpus, "clip")
    output = tmp_path / "output"
    pipeline = _pipeline()
    pipeline.config = replace(
        pipeline.config,
        paths=PathConfig(cache_dir=tmp_path / "cache", output_dir=output),
    )
    assert pipeline.run(corpus, output, None).outcomes[0].status == "aligned"
    artifact = output / "clip"
    assert json.loads((artifact / "alignment.json").read_text(encoding="utf-8"))

    from test_pipeline_fake_backends import ExplodingAccent

    rerun = _pipeline(accent=ExplodingAccent())
    rerun.config = replace(
        rerun.config,
        paths=PathConfig(cache_dir=tmp_path / "rerun-cache", output_dir=output),
    )
    result = rerun.run(corpus, output, None)

    assert result.outcomes[0].status == "failed"
    assert not (artifact / "clip.TextGrid").exists()
    assert not (artifact / "alignment.json").exists()
    assert not (artifact / ".japanmfa.complete").exists()
