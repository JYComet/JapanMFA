from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from japanmfa.domain import UtteranceOutcome
from tools import galgame_mfa_hybrid as hybrid
from tools.galgame_mfa_hybrid import choose_candidate, existing_pair_verified, needs_ctc_fallback


def _outcome(tmp_path: Path, status: str, reason: str | None) -> UtteranceOutcome:
    return UtteranceOutcome("sample", status, reason, None, tmp_path, {})


def test_only_acoustic_or_timestamp_rejections_with_evidence_retry(tmp_path: Path) -> None:
    (tmp_path / "postprocess.json").write_text(json.dumps({"passed": False,
        "reason_code": "timestamp_mfa_disagreement"}))
    assert needs_ctc_fallback(_outcome(tmp_path, "failed", "timestamp_mfa_disagreement"))
    assert not needs_ctc_fallback(_outcome(tmp_path, "failed", "model_unavailable"))
    assert not needs_ctc_fallback(_outcome(tmp_path, "aligned", None))


def test_candidate_selection_never_accepts_failed_crop(tmp_path: Path) -> None:
    passed = _outcome(tmp_path, "aligned", None)
    failed = _outcome(tmp_path, "failed", "alignment_acoustic_coverage")
    assert choose_candidate(passed, failed) == "whole"
    assert choose_candidate(failed, passed) == "anchored"
    assert choose_candidate(failed, failed) is None


def test_existing_grid_without_matching_wav_is_not_retained_as_published(tmp_path: Path) -> None:
    grid = tmp_path / "sample.TextGrid"
    grid.write_text("diagnostic")
    assert not existing_pair_verified(tmp_path, "sample", "expected-hash", lambda path: "wrong-hash")
    (tmp_path / "sample.wav").write_bytes(b"different")
    assert not existing_pair_verified(tmp_path, "sample", "expected-hash", lambda path: "wrong-hash")


def test_failed_new_alignment_retains_verified_previous_pair(tmp_path: Path, monkeypatch) -> None:
    destination = tmp_path / "published"
    destination.mkdir()
    (destination / "sample.TextGrid").write_text("accepted")
    (destination / "sample.wav").write_bytes(b"source")
    run = tmp_path / "run"
    run.mkdir()
    item = SimpleNamespace(utterance_id="sample")
    failed = _outcome(tmp_path, "failed", "model_error")

    class FakePipeline:
        def prepare_mfa_inputs(self, *_args):
            return SimpleNamespace(items=(item,), failures=())

        def run(self, *_args):
            return SimpleNamespace(outcomes=(failed,))

    monkeypatch.setattr(hybrid, "_pipeline", lambda *_args, **_kwargs: FakePipeline())
    combined = SimpleNamespace(root=run, corpus_dir=run, dictionary=run / "dictionary",
                               entries={"wsample": item, "asample": item})
    whole = SimpleNamespace(entries={"wsample": item})
    anchored = SimpleNamespace(entries={"asample": item})
    monkeypatch.setattr(hybrid, "build_dual_batch_corpus",
                        lambda *_args: (combined, whole, anchored), raising=False)
    monkeypatch.setattr(hybrid, "_batch_align", lambda *_args: (
        {"wsample": run / "whole.TextGrid", "asample": run / "anchored.TextGrid"}, 0.0))
    monkeypatch.setattr(hybrid, "BatchGridRunner", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(hybrid, "existing_pair_verified", lambda *_args: True)

    report = hybrid.run_hybrid(
        tmp_path / "input", [{"stem": "sample", "wav_sha256": "source-hash"}],
        run, destination, object(), object(), lambda *_args: {}, lambda *_args: "hash",
    )
    assert report["published_or_retained"] == 1
    assert report["newly_published"] == 0
    assert report["results"][0]["chosen"] is None
    assert report["results"][0]["retained_existing"] is True


def test_hybrid_uses_one_mfa_batch_for_whole_and_anchor_candidates(tmp_path: Path, monkeypatch) -> None:
    run = tmp_path / "run"
    run.mkdir()
    item = SimpleNamespace(utterance_id="sample")
    failed = _outcome(tmp_path, "failed", "model_error")

    class FakePipeline:
        def prepare_mfa_inputs(self, *_args):
            return SimpleNamespace(items=(item,), failures=())

        def run(self, *_args):
            return SimpleNamespace(outcomes=(failed,))

    batch = SimpleNamespace(root=run, corpus_dir=run, dictionary=run / "dictionary",
                            entries={"wsample": item, "asample": item})
    whole = SimpleNamespace(entries={"wsample": item})
    anchored = SimpleNamespace(entries={"asample": item})
    calls = []
    monkeypatch.setattr(hybrid, "_pipeline", lambda *_args, **_kwargs: FakePipeline())
    monkeypatch.setattr(hybrid, "build_dual_batch_corpus", lambda *_args: (batch, whole, anchored),
                        raising=False)
    monkeypatch.setattr(hybrid, "_batch_align", lambda *_args: (
        calls.append(1) or {"wsample": run / "whole.TextGrid",
                            "asample": run / "anchored.TextGrid"}, 1.0))
    monkeypatch.setattr(hybrid, "BatchGridRunner", lambda *_args, **_kwargs: object())

    report = hybrid.run_hybrid(
        tmp_path / "input", [{"stem": "sample", "wav_sha256": "hash"}], run,
        tmp_path / "published", object(), object(), lambda *_args: {}, lambda *_args: "hash",
    )
    assert len(calls) == 1
    assert report["mfa_batches"]["combined"]["files"] == 2
