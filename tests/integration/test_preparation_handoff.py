from dataclasses import replace
from pathlib import Path
import hashlib

from japanmfa.pipeline import JapanMFAPipeline
from test_pipeline_fake_backends import _pipeline, _write_audio


def test_prepared_review_runs_frontend_audio_and_native_preparation_once(tmp_path):
    inp = tmp_path / "input"
    _write_audio(inp, "one")
    pipeline = _pipeline()
    pipeline.config = replace(pipeline.config, paths=replace(pipeline.config.paths, cache_dir=tmp_path / "cache"))
    calls = []
    for obj, name in [(pipeline.audio_normalizer, "prepare"), (pipeline.asr_client, "transcribe"),
                      (pipeline.frontend, "analyze"), (pipeline.accent_client, "predict"),
                      (pipeline.g2p_client, "pronounce")]:
        original = getattr(obj, name)
        def track(*a, _original=original, _name=name, **kw):
            calls.append(_name)
            return _original(*a, **kw)
        setattr(obj, name, track)
    pipeline.batch_preparation = True
    preparation = pipeline.prepare_mfa_inputs(inp, tmp_path / "prepared", None)
    assert len(preparation.items) == 1
    result = pipeline.review_mfa_inputs(preparation, tmp_path / "review")
    assert result.outcomes[0].status == "aligned"
    assert calls == ["prepare", "transcribe", "analyze", "predict", "pronounce"]
    baseline = _pipeline()
    baseline.config = replace(baseline.config, paths=replace(baseline.config.paths, cache_dir=tmp_path / "baseline-cache"))
    expected = baseline.run(inp, tmp_path / "baseline", None)
    assert expected.outcomes[0].status == "aligned"
    assert (tmp_path / "baseline/one/one.TextGrid").read_bytes() == (tmp_path / "review/one/one.TextGrid").read_bytes()


def test_prepared_review_rejects_changed_source(tmp_path):
    inp = tmp_path / "input"
    _write_audio(inp, "one")
    pipeline = _pipeline()
    pipeline.config = replace(pipeline.config, paths=replace(pipeline.config.paths, cache_dir=tmp_path / "cache"))
    preparation = pipeline.prepare_mfa_inputs(inp, tmp_path / "prepared", None)
    (inp / "one.txt").write_text("変更", encoding="utf-8")
    result = pipeline.review_mfa_inputs(preparation, tmp_path / "review")
    assert result.outcomes[0].status == "failed"
    assert result.outcomes[0].reason_code == "prepared_source_changed"
    assert not (tmp_path / "review/one/one.TextGrid").exists()


def test_review_rejects_overlapping_source_output_before_cleanup(tmp_path):
    import pytest
    inp = tmp_path / "input"
    _write_audio(inp, "one")
    pipeline = _pipeline()
    pipeline.config = replace(pipeline.config, paths=replace(pipeline.config.paths, cache_dir=tmp_path / "cache"))
    preparation = pipeline.prepare_mfa_inputs(inp, tmp_path / "prepared", None)
    original = (inp / "one.wav").read_bytes()
    with pytest.raises(ValueError, match="overlap"):
        pipeline.review_mfa_inputs(preparation, inp)
    assert (inp / "one.wav").read_bytes() == original


def test_handoff_rejects_changed_ctc_dictionary_and_working_audio(tmp_path):
    for changed in ("ctc", "dictionary", "working"):
        root = tmp_path / changed
        inp = root / "input"; _write_audio(inp, "one")
        ctc = root / "one.TextGrid"; ctc.write_text("original")
        pipeline = _pipeline()
        pipeline.asr_client.grids = {"one": str(ctc)}
        pipeline.config = replace(pipeline.config, paths=replace(pipeline.config.paths, cache_dir=root / "cache"))
        preparation = pipeline.prepare_mfa_inputs(inp, root / "prepared", None)
        item = preparation.items[0]
        target = {"ctc":ctc, "dictionary":item.dictionary, "working":item.working_audio}[changed]
        target.write_bytes(target.read_bytes()+b"changed")
        result = pipeline.review_mfa_inputs(preparation, root / "review")
        assert result.outcomes[0].reason_code == "prepared_source_changed"
        assert not (root / "review/one/one.TextGrid").exists()


def test_prepared_review_manifest_covers_preparation_failures(tmp_path):
    import json
    from japanmfa.domain import UtteranceOutcome
    from japanmfa.pipeline import MfaPreparationBatch
    inp = tmp_path / "input"; _write_audio(inp, "one")
    pipeline = _pipeline()
    pipeline.config = replace(pipeline.config, paths=replace(pipeline.config.paths, cache_dir=tmp_path / "cache"))
    prepared = pipeline.prepare_mfa_inputs(inp, tmp_path / "prepared", None)
    failed = UtteranceOutcome("bad", "failed", "native_failure", "original failure", None, {})
    result = pipeline.review_mfa_inputs(MfaPreparationBatch(prepared.items, (failed,)), tmp_path / "review")
    rows = [json.loads(line) for line in result.manifest_path.read_text().splitlines()]
    assert len(rows) == len(result.outcomes) == 2
    assert {row["utterance_id"] for row in rows} == {"one", "bad"}
    assert next(row for row in rows if row["utterance_id"] == "bad")["reason_code"] == "native_failure"
