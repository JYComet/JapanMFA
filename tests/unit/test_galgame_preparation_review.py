from types import SimpleNamespace
from japanmfa.domain import UtteranceOutcome
from tools import galgame_mfa_hybrid as hybrid

def test_whole_review_excludes_failed_preparation_and_preserves_reason(tmp_path, monkeypatch):
    stage = tmp_path / "input"
    stage.mkdir()
    run = tmp_path / "run"
    run.mkdir()
    for stem in ("ready", "blocked"):
        for ext in (".wav", ".txt"):
            (stage / (stem + ext)).write_bytes(b"unchanged source")
    ready = SimpleNamespace(utterance_id="ready")
    failure = UtteranceOutcome("blocked", "failed", "no_mappable_pronunciation", None, run, {})
    class FakePipeline:
        def prepare_mfa_inputs(self, *_args):
            return SimpleNamespace(items=(ready,), failures=(failure,))
        def run(self, input_root, *_args):
            assert {p.stem for p in input_root.glob("*.wav")} == {"ready"}
            assert (input_root / "ready.wav").read_bytes() == b"unchanged source"
            assert (input_root / "ready.txt").read_bytes() == b"unchanged source"
            return SimpleNamespace(outcomes=(UtteranceOutcome("ready", "failed", "model_error", None, run, {}),))
    monkeypatch.setattr(hybrid, "_pipeline", lambda *_args, **_kwargs: FakePipeline())
    combined = SimpleNamespace(root=run, corpus_dir=run, dictionary=run / "dictionary", entries={"wready": ready, "aready": ready})
    whole = SimpleNamespace(entries={"wready": ready})
    anchored = SimpleNamespace(entries={"aready": ready})
    monkeypatch.setattr(hybrid, "build_dual_batch_corpus", lambda *_args: (combined, whole, anchored))
    monkeypatch.setattr(hybrid, "_batch_align", lambda *_args: ({"wready": run / "w.TextGrid", "aready": run / "a.TextGrid"}, 0.0))
    monkeypatch.setattr(hybrid, "BatchGridRunner", lambda *_args, **_kwargs: object())
    report = hybrid.run_hybrid(stage, [{"stem": "ready", "wav_sha256": "hash"}, {"stem": "blocked", "wav_sha256": "hash"}], run, tmp_path / "output", object(), object(), lambda *_args: {}, lambda *_args: "hash")
    rows = {row["stem"]: row for row in report["results"]}
    assert rows["blocked"]["whole_reason"] == "no_mappable_pronunciation"
    assert rows["blocked"]["anchored_attempted"] is False
    assert report["published_or_retained"] == 0
