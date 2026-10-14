from pathlib import Path
from dataclasses import replace
import json

import pytest

from japanmfa.cache import StageCache
from japanmfa.domain import Pronunciation, Token
from japanmfa.errors import StageFailure
from japanmfa.pipeline import JapanMFAPipeline
from test_pipeline_fake_backends import _pipeline, _write_audio


class Frontend:
    def analyze(self, source):
        reading = "キョオ" if source.original == "京" else "キョウ"
        return (Token(0, 0, len(source.original), source.original, ("名詞",), reading, "sudachi"),)


def make_pipeline(root, *, batch, accent_calls, g2p_calls, malformed=False, transport_failure=False, g2p_failure=False):
    base = _pipeline()
    class Accent:
        def predict(self, requests):
            accent_calls.append(tuple((r.token_index, r.surface, r.yomi) for r in requests))
            if transport_failure and any(r.surface == "京" for r in requests):
                raise StageFailure("accent", "empty_output", "bad line")
            return {r.token_index: ("キョ[[オ" if malformed and r.surface == "京" else r.yomi[:-1] + "[" + r.yomi[-1]) for r in requests}
    class G2p:
        def pronounce(self, readings, work):
            g2p_calls.append(tuple(readings))
            if g2p_failure and "キョオ" in readings:
                raise StageFailure("mfa_g2p", "missing_pronunciation", "missing locked reading")
            work.mkdir(parents=True, exist_ok=True)
            (work / "g2p_input.txt").write_text("\n".join(readings) + "\n")
            ps = tuple(Pronunciation(x, ("k", "jo", "o" if x == "キョオ" else "u"), (("k", "jo", "a"),)) for x in readings)
            (work / "g2p_output.dict").write_text("".join(p.reading + " " + " ".join(p.phones) + "\n" for p in ps))
            return ps
    return JapanMFAPipeline(
        replace(base.config, paths=replace(base.config.paths, cache_dir=root / "cache")),
        audio_normalizer=base.audio_normalizer, asr_client=base.asr_client,
        frontend=Frontend(), accent_client=Accent(), g2p_client=G2p(),
        mfa_runner=base.mfa_runner, phone_map=base.phone_map, batch_preparation=batch,
    )


def sources(root):
    for name, text in [("one", "今日"), ("two", "京"), ("three", "強")]:
        _write_audio(root, name, text)


def snapshot(root):
    return {p.relative_to(root).as_posix(): json.loads(p.read_text()) for stage in ("accent", "g2p") for p in (root / stage).glob("*/result.json")}


def test_bulk_is_identical_to_serial_and_warm_cache_skips_calls(tmp_path):
    inp = tmp_path / "input"; sources(inp)
    serial_accent, serial_g2p, batch_accent, batch_g2p = [], [], [], []
    serial = make_pipeline(tmp_path / "serial", batch=False, accent_calls=serial_accent, g2p_calls=serial_g2p)
    bulk = make_pipeline(tmp_path / "bulk", batch=True, accent_calls=batch_accent, g2p_calls=batch_g2p)
    a = serial.prepare_mfa_inputs(inp, tmp_path / "serial-out", None)
    b = bulk.prepare_mfa_inputs(inp, tmp_path / "bulk-out", None)
    assert len(a.items) == len(b.items) == 3
    assert a.failures == b.failures == ()
    assert len(serial_accent) == len(serial_g2p) == 3
    assert len(batch_accent) == len(batch_g2p) == 1
    assert len({r[0] for r in batch_accent[0]}) == 3
    assert batch_g2p[0].count("キョウ") == 1
    assert snapshot(tmp_path / "serial/cache") == snapshot(tmp_path / "bulk/cache")
    for stem in ("one", "two", "three"):
        for name in ("frontend.json", "mora.json", "mfa/dictionary.dict", "mfa/corpus/aliases.json"):
            assert (tmp_path / "serial-out" / stem / name).read_bytes() == (tmp_path / "bulk-out" / stem / name).read_bytes()
    bulk.prepare_mfa_inputs(inp, tmp_path / "warm-out", None)
    assert len(batch_accent) == len(batch_g2p) == 1


@pytest.mark.parametrize("mode", ["transport_failure", "g2p_failure"])
def test_bad_source_stays_isolated_with_same_serial_reason(tmp_path, mode):
    inp = tmp_path / "input"; sources(inp)
    results = []
    for batch in (False, True):
        root = tmp_path / str(batch)
        pipeline = make_pipeline(root, batch=batch, accent_calls=[], g2p_calls=[], **{mode: True})
        result = pipeline.prepare_mfa_inputs(inp, root / "out", None)
        results.append(({x.utterance_id for x in result.items}, [(x.utterance_id, x.reason_code) for x in result.failures]))
    assert results[0] == results[1]
    assert results[1][0] == {"one", "three"}
    assert len(results[1][1]) == 1


def test_malformed_accent_with_intact_reading_reaches_g2p_in_serial_and_bulk(tmp_path):
    inp = tmp_path / "input"; sources(inp)
    for batch in (False, True):
        root = tmp_path / str(batch)
        pipeline = make_pipeline(root, batch=batch, accent_calls=[], g2p_calls=[], malformed=True)
        result = pipeline.prepare_mfa_inputs(inp, root / "out", None)
        assert {item.utterance_id for item in result.items} == {"one", "two", "three"}
        assert result.failures == ()
        mora = json.loads((root / "out/two/mora.json").read_text())
        assert mora["tdmelodic"] == {"0": "キョ[[オ"}
        assert [m["tone"] for m in mora["morae"][0]["morae"]] == [None, None]
        assert mora["unknown_tone_indices"] == {"0": "malformed_output_exact_reading"}


@pytest.mark.parametrize("reading", ["メェェ", "ュ", "ッャ"])
def test_unsupported_mora_isolated_without_poisoning_other_sources(tmp_path, reading):
    inp = tmp_path / "input"; sources(inp)
    class UnsupportedFrontend(Frontend):
        def analyze(self, source):
            tokens = super().analyze(source)
            return tuple(replace(t, reading=reading) if source.original == "京" else t for t in tokens)
    results = []
    for batch in (False, True):
        root = tmp_path / str(batch)
        pipeline = make_pipeline(root, batch=batch, accent_calls=[], g2p_calls=[])
        pipeline.frontend = UnsupportedFrontend()
        result = pipeline.prepare_mfa_inputs(inp, root / "out", None)
        results.append(({x.utterance_id for x in result.items},
                        [(x.utterance_id, x.reason_code) for x in result.failures]))
        # Unsupported source must never receive a successful accent cache entry.
        assert len(list((root / "cache/accent").glob("*/complete.json"))) == 2
    assert results[0] == results[1]
    assert results[1][0] == {"one", "three"}
    assert results[1][1] == [("two", "unexpected_exception")]
