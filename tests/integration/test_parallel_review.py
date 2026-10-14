"""The review scheduler may change; each utterance's result may not."""

import json
import os
import time

import pytest

from japanmfa.pipeline import JapanMFAPipeline
from japanmfa.config import PipelineConfig
from test_pipeline_fake_backends import EchoAccent, FakeMfa, _pipeline, _write_audio
from tools import galgame_mfa_hybrid


class ProcessMfa(FakeMfa):
    def align(self, corpus_dir, dictionary, output_dir, work_dir):
        time.sleep(.2)
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        (output_dir.parent / 'review.pid').write_text(str(os.getpid()))
        return super().align(corpus_dir, dictionary, output_dir, work_dir)


def test_parallel_review_matches_serial_grids_reasons_and_manifest_order(tmp_path):
    corpus = tmp_path / "input"
    for stem in ("d", "b", "a", "c"):
        _write_audio(corpus, stem)
    _write_audio(corpus, "blocked", text="Tokyo")
    preparation = _pipeline(accent=EchoAccent()).prepare_mfa_inputs(corpus, tmp_path / "prepared", None)

    serial = _pipeline(accent=EchoAccent()).review_mfa_inputs(preparation, tmp_path / "serial")
    parallel_pipeline = _pipeline(accent=EchoAccent())
    parallel_pipeline.review_workers = 4
    parallel = parallel_pipeline.review_mfa_inputs(preparation, tmp_path / "parallel")

    def semantic(result):
        return [(item.utterance_id, item.status, item.reason_code) for item in result.outcomes]

    assert semantic(serial) == semantic(parallel)
    assert semantic(serial) == [
        ("blocked", "skipped", "unsupported_japanese_text"),
        ("a", "aligned", None), ("b", "aligned", None),
        ("c", "aligned", None), ("d", "aligned", None),
    ]
    for stem in "abcd":
        assert (tmp_path / "serial" / stem / f"{stem}.TextGrid").read_bytes() == (
            tmp_path / "parallel" / stem / f"{stem}.TextGrid").read_bytes()
    for result in (serial, parallel):
        rows = [json.loads(line) for line in result.manifest_path.read_text().splitlines()]
        assert [row["utterance_id"] for row in rows] == ["blocked", "a", "b", "c", "d"]


def test_review_workers_run_at_the_same_time(tmp_path):
    corpus = tmp_path / "input"
    for stem in "abcd":
        _write_audio(corpus, stem)
    preparation = _pipeline(accent=EchoAccent()).prepare_mfa_inputs(corpus, tmp_path / "prepared", None)
    pipeline = _pipeline(accent=EchoAccent(), mfa=ProcessMfa())
    pipeline.review_workers = 4

    result = pipeline.review_mfa_inputs(preparation, tmp_path / "parallel")

    assert [(item.utterance_id, item.status) for item in result.outcomes] == [
        ("a", "aligned"), ("b", "aligned"), ("c", "aligned"), ("d", "aligned")]
    pids = {int((tmp_path / 'parallel' / stem / 'mfa' / 'review.pid').read_text()) for stem in 'abcd'}
    assert len(pids) >= 2
    assert os.getpid() not in pids


def test_review_worker_count_is_bounded():
    with pytest.raises(ValueError, match="review workers"):
        JapanMFAPipeline(review_workers=3)


def test_galgame_review_worker_setting_is_explicit(monkeypatch):
    monkeypatch.setenv("JAPANMFA_REVIEW_WORKERS", "4")
    assert galgame_mfa_hybrid._pipeline(PipelineConfig(), object()).review_workers == 4
    monkeypatch.delenv("JAPANMFA_REVIEW_WORKERS")
    assert galgame_mfa_hybrid._pipeline(PipelineConfig(), object()).review_workers == 1


def test_parallel_review_accepts_cache_without_root_attribute(tmp_path):
    corpus = tmp_path / 'input'
    _write_audio(corpus, 'ok')
    preparation = _pipeline(accent=EchoAccent()).prepare_mfa_inputs(corpus, tmp_path/'prepared', None)
    pipeline = _pipeline(accent=EchoAccent())
    pipeline.review_workers = 2
    pipeline.cache = object()

    result = pipeline.review_mfa_inputs(preparation, tmp_path/'parallel')

    assert [(item.utterance_id, item.status) for item in result.outcomes] == [('ok', 'aligned')]
