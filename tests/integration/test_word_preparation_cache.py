from dataclasses import replace
from pathlib import Path
import json
from test_bulk_preparation import make_pipeline
from test_pipeline_fake_backends import _write_audio


def test_new_sources_reuse_exact_words_across_batches_and_preserve_alternates(tmp_path):
    ac, gc = [], []
    pipeline = make_pipeline(tmp_path, batch=True, accent_calls=ac, g2p_calls=gc)
    from japanmfa.domain import Token
    class Repeated:
        def analyze(self, source):
            return tuple(Token(i, 2*i, 2*i+2, "今日", ("名詞",), "キョウ", "sudachi")
                         for i in range(len(source.original)//2))
    pipeline.frontend = Repeated()
    for index in range(2):
        inp = tmp_path / f"input-{index}"
        _write_audio(inp, f"one-{index}", "今日"*(index+1))
        result = pipeline.prepare_mfa_inputs(inp, tmp_path / f"out-{index}", None)
        assert len(result.items) == 1
    assert len(ac) == len(gc) == 1
    # Model identity changes invalidate G2P, even when the exact reading is the same.
    pipeline.config = replace(pipeline.config, mfa=replace(pipeline.config.mfa, g2p_model="different-model"))
    inp = tmp_path / "third"; _write_audio(inp, "third", "今日")
    assert len(pipeline.prepare_mfa_inputs(inp, tmp_path / "out-third", None).items) == 1
    assert len(gc) == 2


def test_controlled_partial_accent_does_not_repeat_valid_requests(tmp_path):
    ac, gc = [], []
    pipeline = make_pipeline(tmp_path, batch=True, accent_calls=ac, g2p_calls=gc)
    class Partial:
        def predict_partial(self, requests):
            ac.append(tuple(r.surface for r in requests))
            return ({r.token_index: r.yomi[:-1]+"["+r.yomi[-1] for r in requests if r.surface != "京"},
                    {r.token_index: "empty_output" for r in requests if r.surface == "京"})
        def predict(self, requests):
            raise AssertionError("partial rejection must not repeat the whole group")
    pipeline.accent_client = Partial()
    inp = tmp_path / "input"
    for name,text in [("one","今日"),("two","京"),("three","強")]: _write_audio(inp,name,text)
    result = pipeline.prepare_mfa_inputs(inp, tmp_path/"out", None)
    assert {x.utterance_id for x in result.items} == {"one", "three"}
    assert [(x.utterance_id,x.reason_code) for x in result.failures] == [("two","empty_output")]
    assert len(ac) == 1
    assert len(gc) == 1


def test_validated_untoned_native_word_is_reused_without_recomputation(tmp_path):
    ac,gc=[],[]
    pipeline=make_pipeline(tmp_path,batch=True,accent_calls=ac,g2p_calls=gc,malformed=True)
    inp=tmp_path/"input"
    for name,text in [("one","今日"),("two","京"),("three","強")]: _write_audio(inp,name,text)
    result=pipeline.prepare_mfa_inputs(inp,tmp_path/"out",None)
    assert {x.utterance_id for x in result.items}=={"one","two","three"}
    assert result.failures==()
    assert len(ac)==1
    second=tmp_path/"second"
    _write_audio(second,"again","京")
    assert len(pipeline.prepare_mfa_inputs(second,tmp_path/"second-out",None).items)==1
    assert len(ac)==1


def test_batch_preparation_records_native_repair_evidence(tmp_path):
    pipeline = make_pipeline(tmp_path, batch=True, accent_calls=[], g2p_calls=[])
    repair = {"raw": "キョ]ウ", "marked": "キョ[ウ", "accent": 0, "evidence": "exact-lexicon"}
    class Detailed:
        def predict_partial_detailed(self, requests):
            return ({r.token_index: r.yomi[:-1] + "[" + r.yomi[-1] for r in requests},
                    {}, {r.token_index: repair for r in requests if r.surface == "今日"})
    pipeline.accent_client = Detailed()
    inp = tmp_path / "input"
    _write_audio(inp, "one", "今日")
    result = pipeline.prepare_mfa_inputs(inp, tmp_path / "out", None)
    assert len(result.items) == 1
    evidence = next((tmp_path / "out").rglob("batch-native-preparation/accent-*/outputs.json"))
    assert json.loads(evidence.read_text())["repairs"] == {"0": repair}
