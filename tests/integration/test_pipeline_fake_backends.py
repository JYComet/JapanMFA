from __future__ import annotations

from dataclasses import dataclass
import json
import array
import math
import wave
from pathlib import Path

import pytest
import yaml
from praatio import textgrid as praat_textgrid

from japanmfa.audio import AudioInfo
from japanmfa.accent.tdmelodic import resolve_tdmelodic_command
from japanmfa.config import PipelineConfig
from japanmfa.domain import Pronunciation, SourceText, Token
from japanmfa.errors import StageFailure, SkipUtterance
from japanmfa.frontend.mora import segment_morae
from japanmfa.mfa.phone_map import PhoneMap
from japanmfa.pipeline import JapanMFAPipeline
from japanmfa.pipeline import _punctuation_groups


_GRID = '''File type = "ooTextFile"
Object class = "TextGrid"
xmin = 0
xmax = 1
tiers? <exists>
size = 2
item []:
    item [1]:
        class = "IntervalTier"
        name = "words"
        xmin = 0
        xmax = 1
        intervals: size = 1
        intervals [1]:
            xmin = 0
            xmax = 1
            text = "jmfa_000000"
    item [2]:
        class = "IntervalTier"
        name = "phones"
        xmin = 0
        xmax = 1
        intervals: size = 3
        intervals [1]:
            xmin = 0
            xmax = 0.3
            text = "k"
        intervals [2]:
            xmin = 0.3
            xmax = 0.6
            text = "jo"
        intervals [3]:
            xmin = 0.6
            xmax = 1
            text = "u"
'''


class FakeAudio:
    def prepare(self, source: Path, destination: Path) -> AudioInfo:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
        return AudioInfo(source, destination, 1.0, 16000, 1, 16000)


class FakeAsr:
    def __init__(self, text: str = "今日は晴れ") -> None:
        self.text = text

    def transcribe(self, paths: list[Path], *, reference_texts=None) -> dict[Path, object]:
        from japanmfa.asr.qwen3 import ASRResult

        return {path: ASRResult(path, "Japanese", self.text, "fake") for path in paths}


class NonJapaneseErrorAsr:
    def transcribe(self, _paths: list[Path], *, reference_texts=None) -> dict[Path, object]:
        raise StageFailure("asr", "non_japanese_language", "Qwen detected English")


class FakeFrontend:
    def analyze(self, source: SourceText) -> tuple[Token, ...]:
        if "Tokyo" in source.processing:
            raise SkipUtterance("unsupported_japanese_text", "Latin text")
        return (Token(0, 0, 2, "今日", ("名詞",), "キョウ", "sudachi"),)


class FakeAccent:
    def __init__(self, malformed: bool = False) -> None:
        self.malformed = malformed

    def predict(self, _requests: object) -> dict[int, str]:
        if self.malformed:
            raise StageFailure("accent", "malformed_output", "bad tdmelodic")
        return {0: "キョ[ウ"}


class EchoAccent:
    def predict(self, requests: object) -> dict[int, str]:
        return {
            int(request.token_index): f"{request.yomi[:-1]}[{request.yomi[-1]}"
            for request in requests
        }


class ExplodingAccent:
    def predict(self, _requests: object) -> dict[int, str]:
        raise RuntimeError("OPENAI_API_KEY=super-secret-token")


class FakeG2p:
    def pronounce(self, readings: tuple[str, ...], _work_dir: Path) -> tuple[Pronunciation, ...]:
        return tuple(Pronunciation(reading, ("k", "jo", "u")) for reading in readings)


class OccurrenceG2p:
    def pronounce(self, readings: tuple[str, ...], _work_dir: Path) -> tuple[Pronunciation, ...]:
        phones = {"キョウ": ("k", "jo", "u"), "キョオ": ("k", "jo", "o")}
        return tuple(Pronunciation(reading, phones[reading]) for reading in readings)


class FakeMfa:
    def __init__(self, fail_for: str | None = None) -> None:
        self.fail_for = fail_for

    def align(self, corpus_dir: Path, _dictionary: Path, output_dir: Path, _work_dir: Path) -> Path:
        if self.fail_for and self.fail_for in str(corpus_dir):
            raise StageFailure("mfa", "command_failed", "fake alignment failure")
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "aligned.TextGrid"
        path.write_text(_GRID, encoding="utf-8")
        return path


class OccurrenceMfa:
    def align(self, _corpus_dir: Path, dictionary: Path, output_dir: Path, _work_dir: Path) -> Path:
        phones = dictionary.read_text(encoding="utf-8").split()[1:]
        width = 1 / len(phones)
        intervals = "\n".join(
            f"""        intervals [{index}]:
            xmin = {index * width:.6f}
            xmax = {(index + 1) * width:.6f}
            text = \"{phone}\""""
            for index, phone in enumerate(phones, start=0)
        )
        grid = f'''File type = "ooTextFile"
Object class = "TextGrid"
xmin = 0
xmax = 1
tiers? <exists>
size = 2
item []:
    item [1]:
        class = "IntervalTier"
        name = "words"
        xmin = 0
        xmax = 1
        intervals: size = 1
        intervals [1]:
            xmin = 0
            xmax = 1
            text = "jmfa_000000"
    item [2]:
        class = "IntervalTier"
        name = "phones"
        xmin = 0
        xmax = 1
        intervals: size = {len(phones)}
{intervals}
'''
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "aligned.TextGrid"
        path.write_text(grid, encoding="utf-8")
        return path


def _pipeline(*, accent: object | None = None, g2p: object | None = None, mfa: object | None = None, asr: object | None = None) -> JapanMFAPipeline:
    return JapanMFAPipeline(
        config=PipelineConfig(),
        audio_normalizer=FakeAudio(),
        asr_client=asr or FakeAsr(),
        frontend=FakeFrontend(),
        accent_client=accent or FakeAccent(),
        g2p_client=g2p or FakeG2p(),
        mfa_runner=mfa or FakeMfa(),
        phone_map=PhoneMap.load(Path(__file__).parents[2] / "src" / "japanmfa" / "mfa" / "data" / "japanese_mfa_v3_phone_map.yaml"),
    )


def _write_audio(root: Path, name: str, text: str | None = "今日は晴れ") -> None:
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{name}.wav"
    samples = array.array("h", (int(8000 * math.sin(2 * math.pi * 200 * i / 16000)) for i in range(16000)))
    with wave.open(str(path), "wb") as audio:
        audio.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        audio.writeframes(samples.tobytes())
    if text is not None:
        path.with_suffix(".txt").write_text(text, encoding="utf-8")


def test_fake_backends_write_valid_word_and_phone_tiers_and_reports(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    _write_audio(corpus, "ok")

    result = _pipeline().run(corpus, tmp_path / "output", None)

    assert result.summary["counts"] == {"aligned": 1, "failed": 0, "skipped": 0}
    artifact = tmp_path / "output" / "ok"
    assert (artifact / "ok.TextGrid").is_file()
    from japanmfa.output.textgrid import _parse
    _, _, tiers = _parse(artifact / "ok.TextGrid")
    assert [tier.name for tier in tiers] == [
        "original", "kana", "words", "phones", "phone_kana", "phone_tone",
    ]
    assert [entry.label for entry in tiers[2].intervals] == ["今日"]
    assert all((artifact / name).is_file() for name in ("alignment.json", "frontend.json", "asr.json", "mfa.json"))
    mfa_receipt = json.loads((artifact / "mfa.json").read_text(encoding="utf-8"))
    assert mfa_receipt["timestamp_segments"][0]["aliases"] == ["jmfa_000000"]
    assert (artifact / "ok.wav").is_file()
    assert (artifact / "audio.json").is_file()
    marker = json.loads((artifact / ".japanmfa.complete").read_text(encoding="utf-8"))
    alignment = json.loads((artifact / "alignment.json").read_text(encoding="utf-8"))
    receipt = json.loads((artifact / "audio.json").read_text(encoding="utf-8"))
    assert marker["audio"].endswith("ok.wav")
    assert marker["audio_receipt"].endswith("audio.json")
    assert alignment["audio_sha256"] == receipt["working_sha256"]
    assert alignment["audio_frames"] == receipt["working_frames"]
    assert '"status": "aligned"' in (tmp_path / "output" / "manifest.jsonl").read_text()


def test_whole_mode_uses_full_wav_and_still_reviews_ctc(tmp_path: Path) -> None:
    from japanmfa.asr.qwen3 import ASRResult, Timestamp

    class TimedAsr:
        def transcribe(self, paths, *, reference_texts=None):
            return {path: ASRResult(path, "Japanese", "今日", "fake", "ctc", "今日",
                                    (Timestamp("今日", .3, .7),), ()) for path in paths}

    class RecordingMfa(FakeMfa):
        def __init__(self):
            super().__init__()
            self.frames = []

        def align(self, corpus_dir, dictionary, output_dir, work_dir):
            with wave.open(str(next(corpus_dir.glob("*.wav"))), "rb") as audio:
                self.frames.append(audio.getnframes())
            return super().align(corpus_dir, dictionary, output_dir, work_dir)

    corpus = tmp_path / "corpus"
    _write_audio(corpus, "ok", "今日")
    runner = RecordingMfa()
    pipeline = _pipeline(mfa=runner, asr=TimedAsr())
    pipeline.alignment_mode = "whole"
    result = pipeline.run(corpus, tmp_path / "output", None)

    assert runner.frames == [16000]
    report = json.loads((tmp_path / "output" / "ok" / "postprocess.json").read_text())
    assert "timestamp_alignment" in report
    mfa_receipt = json.loads((tmp_path / "output" / "ok" / "mfa.json").read_text())
    assert "/segments/" not in mfa_receipt["textgrid"]
    assert result.outcomes[0].status == "aligned"


def test_ctc_word_fusion_keeps_phone_tiers_on_one_axis(tmp_path: Path) -> None:
    from japanmfa.asr.qwen3 import ASRResult, Timestamp
    from japanmfa.output.textgrid import _parse

    class TimedAsr:
        def transcribe(self, paths, *, reference_texts=None):
            return {path: ASRResult(path, "Japanese", "今日", "fake", "ctc", "今日",
                                    (Timestamp("今日", .2, .5),), ()) for path in paths}

    class PaddedMfa(FakeMfa):
        def align(self, corpus_dir, dictionary, output_dir, work_dir):
            path = super().align(corpus_dir, dictionary, output_dir, work_dir)
            grid = path.read_text().replace(
                'xmin = 0\n            xmax = 1\n            text = "jmfa_000000"',
                'xmin = 0.2\n            xmax = 0.7\n            text = "jmfa_000000"',
            ).replace('xmin = 0\n            xmax = 0.3\n            text = "k"',
                      'xmin = 0.2\n            xmax = 0.35\n            text = "k"').replace(
                'xmin = 0.3\n            xmax = 0.6\n            text = "jo"',
                'xmin = 0.35\n            xmax = 0.5\n            text = "jo"',
            ).replace('xmin = 0.6\n            xmax = 1\n            text = "u"',
                      'xmin = 0.5\n            xmax = 0.7\n            text = "u"')
            path.write_text(grid)
            return path

    corpus = tmp_path / "corpus"
    _write_audio(corpus, "ok", "今日")
    samples = array.array("h", [0] * 16000)
    for index in range(round(.2 * 16000), round(.55 * 16000)):
        samples[index] = int(8000 * math.sin(2 * math.pi * 200 * index / 16000))
    with wave.open(str(corpus / "ok.wav"), "wb") as audio:
        audio.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        audio.writeframes(samples.tobytes())
    pipeline = _pipeline(mfa=PaddedMfa(), asr=TimedAsr())
    pipeline.alignment_mode = "whole"

    outcome = pipeline.run(corpus, tmp_path / "output", None).outcomes[0]

    assert outcome.status == "aligned"
    artifact = tmp_path / "output" / "ok"
    report = json.loads((artifact / "postprocess.json").read_text())
    assert report["ctc_word_fusion"]["edits"][0]["edge"] == "end"
    _, _, tiers = _parse(artifact / "ok.TextGrid")
    words = next(tier for tier in tiers if tier.name == "words")
    phones = next(tier for tier in tiers if tier.name == "phones")
    kana = next(tier for tier in tiers if tier.name == "phone_kana")
    tone = next(tier for tier in tiers if tier.name == "phone_tone")
    assert words.intervals[1].end <= .6
    assert [(x.start, x.end) for x in phones.intervals] == [
        (x.start, x.end) for x in kana.intervals
    ] == [(x.start, x.end) for x in tone.intervals]


def test_prepare_mfa_inputs_locks_words_without_running_mfa(tmp_path: Path) -> None:
    class ForbiddenMfa:
        def align(self, *args):
            raise AssertionError("preparation must not align")

    corpus = tmp_path / "corpus"
    _write_audio(corpus, "ok")
    prepared = _pipeline(mfa=ForbiddenMfa()).prepare_mfa_inputs(
        corpus, tmp_path / "prepared", None,
    )

    assert not prepared.failures
    assert len(prepared.items) == 1
    item = prepared.items[0]
    assert item.utterance_id == "ok"
    assert item.aliases == ("jmfa_000000",)
    assert item.corpus_audio.is_file()
    assert item.dictionary.is_file()
    assert not (item.artifact_dir / "ok.TextGrid").exists()


def test_punctuation_groups_preserve_consecutive_source_order() -> None:
    assert _punctuation_groups("今日は！？…") == ("！？…",)
    assert _punctuation_groups("ー") == ()


def test_unowned_audio_activity_blocks_publication_without_boundary_movement(tmp_path: Path) -> None:
    class LateMfa(FakeMfa):
        def align(self, *args: object) -> Path:
            path = super().align(*args)
            grid = path.read_text().replace('xmin = 0\n            xmax = 0.3', 'xmin = 0.7\n            xmax = 0.8').replace('xmin = 0.3\n            xmax = 0.6', 'xmin = 0.8\n            xmax = 0.9').replace('xmin = 0.6\n            xmax = 1', 'xmin = 0.9\n            xmax = 1')
            path.write_text(grid)
            return path
    corpus = tmp_path / "corpus"
    _write_audio(corpus, "late")
    result = _pipeline(mfa=LateMfa()).run(corpus, tmp_path / "output", None)
    assert result.outcomes[0].status == "failed"
    assert result.outcomes[0].reason_code == "alignment_acoustic_coverage"
    artifact = tmp_path / "output" / "late"
    audit = json.loads((artifact / "postprocess.json").read_text())
    assert audit["structural_issues"]
    assert audit["synthetic_silence_speech_regions"]
    assert not (artifact / "late.TextGrid").exists()
    assert not (artifact / "alignment.json").exists()
    assert not (artifact / ".japanmfa.complete").exists()


def test_successful_pipeline_records_per_phone_mora_tone_trace(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    _write_audio(corpus, "ok")
    assert _pipeline().run(corpus, tmp_path / "output", None).outcomes[0].status == "aligned"
    artifact = tmp_path / "output" / "ok"
    payload = json.loads((artifact / "alignment.json").read_text())
    assert [p["tone"] for p in payload["phones"]] == ["LL", "LL", "HH"]
    assert payload["phones"][0]["morae"] == [{"token_index": 0, "index_in_token": 0, "kana": "キョ", "tone": "L"}]
    assert json.loads((artifact / "postprocess.json").read_text())["passed"]


def test_coverage_failure_is_not_retried_with_boundary_mutation(tmp_path: Path) -> None:
    class RecoveryMfa(FakeMfa):
        def align(self, corpus: Path, dictionary: Path, output: Path, work: Path) -> Path:
            path = super().align(corpus, dictionary, output, work)
            if "recovery" not in corpus.parts:
                path.write_text(_GRID.replace('xmin = 0\n            xmax = 0.3', 'xmin = 0.7\n            xmax = 0.8').replace('xmin = 0.3\n            xmax = 0.6', 'xmin = 0.8\n            xmax = 0.9').replace('xmin = 0.6\n            xmax = 1', 'xmin = 0.9\n            xmax = 1'))
            else:
                aliases = (corpus / "clip.lab").read_text().split()
                assert len(aliases) == 2
                assert [row.split()[1:] for row in dictionary.read_text().splitlines()] == [["k", "jo"], ["u"]]
                replacement = f'''intervals: size = 2
        intervals [1]:
            xmin = 0
            xmax = 0.6
            text = "{aliases[0]}"
        intervals [2]:
            xmin = 0.6
            xmax = 1
            text = "{aliases[1]}"'''
                original = '''intervals: size = 1
        intervals [1]:
            xmin = 0
            xmax = 1
            text = "jmfa_000000"'''
                path.write_text(_GRID.replace(original, replacement))
            return path
    corpus = tmp_path / "corpus"
    _write_audio(corpus, "recover")
    result = _pipeline(mfa=RecoveryMfa()).run(corpus, tmp_path / "output", None)
    assert result.outcomes[0].status == "failed"
    assert result.outcomes[0].reason_code == "alignment_acoustic_coverage"
    artifact = tmp_path / "output" / "recover"
    assert not (artifact / "alignment.json").exists()


def test_batch_writes_resolved_config_and_authoritative_asr_comparison(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JAPANMFA_ASR_MODEL_PATH", "/models/qwen3-asr")
    monkeypatch.setenv("JAPANMFA_REQUIRE_CUDA", "yes")
    corpus = tmp_path / "corpus"
    _write_audio(corpus, "ok", "今日は晴れ")

    result = _pipeline(asr=FakeAsr("今日は雨")).run(corpus, tmp_path / "output", None)

    assert result.summary["counts"] == {"aligned": 1, "failed": 0, "skipped": 0}
    resolved = (tmp_path / "output" / "resolved_config.yaml").read_text(encoding="utf-8")
    resolved_payload = yaml.safe_load(resolved)
    assert "japanmfa:" in resolved
    assert "python:" in resolved
    assert "Qwen/Qwen3-ASR-1.7B" in resolved
    assert "tdmelodic:" in resolved
    assert resolved_payload["paths"]["output_root"] == str((tmp_path / "output").resolve())
    assert resolved_payload["models"]["asr"]["model_path"] == "/models/qwen3-asr"
    assert resolved_payload["device_policy"]["require_cuda"] is True
    manifest_record = json.loads((tmp_path / "output" / "manifest.jsonl").read_text(encoding="utf-8"))
    assert manifest_record["source_type"] == "txt"
    audit = json.loads((tmp_path / "output" / "ok" / "asr.json").read_text(encoding="utf-8"))
    assert audit["source"] == "txt"
    assert audit["comparison"]["equal"] is False
    assert audit["comparison"]["authoritative_normalized"] == "今日は晴れ"
    assert audit["comparison"]["asr_normalized"] == "今日は雨"
    assert audit["comparison"]["difference"]


def test_tdmelodic_runtime_command_uses_shared_environment_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JAPANMFA_TDMELODIC_COMMAND", "docker run --rm -i japanmfa-tdmelodic:test")

    assert resolve_tdmelodic_command() == (
        "docker",
        "run",
        "--rm",
        "-i",
        "japanmfa-tdmelodic:test",
    )
    with pytest.raises(ValueError, match="empty"):
        resolve_tdmelodic_command("")


def test_missing_text_with_non_japanese_asr_is_skipped(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    _write_audio(corpus, "missing", None)

    result = _pipeline(asr=FakeAsr("Tokyo")).run(corpus, tmp_path / "output", None)

    assert result.outcomes[0].status == "skipped"
    assert result.outcomes[0].reason_code == "unsupported_japanese_text"
    record = json.loads((tmp_path / "output" / "manifest.jsonl").read_text(encoding="utf-8"))
    assert record["source_type"] == "asr"


def test_qwen_non_japanese_stage_failure_is_mapped_to_skipped(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    _write_audio(corpus, "missing", None)

    result = _pipeline(asr=NonJapaneseErrorAsr()).run(corpus, tmp_path / "output", None)

    assert result.outcomes[0].status == "skipped"
    assert result.outcomes[0].reason_code == "non_japanese_language"


def test_unexpected_traceback_is_secret_redacted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "super-secret-token")
    corpus = tmp_path / "corpus"
    _write_audio(corpus, "boom")

    result = _pipeline(accent=ExplodingAccent()).run(corpus, tmp_path / "output", None)

    assert result.outcomes[0].reason_code == "unexpected_exception"
    trace = (tmp_path / "output" / "boom" / "traceback.txt").read_text(encoding="utf-8")
    assert "super-secret-token" not in trace


def test_malformed_tdmelodic_fails_one_item_and_continues(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    _write_audio(corpus, "bad")
    _write_audio(corpus, "good")

    result = _pipeline(accent=FakeAccent(malformed=True)).run(corpus, tmp_path / "output", None)

    assert [outcome.status for outcome in result.outcomes] == ["failed", "failed"]
    assert all(outcome.reason_code == "malformed_output" for outcome in result.outcomes)


def test_malformed_pitch_markers_with_intact_reading_publish_explicit_unknown_tone(tmp_path: Path) -> None:
    from japanmfa.cache import StageCache

    class MalformedMarkerAccent:
        def predict(self, _requests):
            return {0: "キョ]ウ["}

    corpus = tmp_path / "corpus"
    _write_audio(corpus, "unknown")

    pipeline = _pipeline(accent=MalformedMarkerAccent())
    pipeline.cache = StageCache(tmp_path / "cache")
    result = pipeline.run(corpus, tmp_path / "output", None)

    assert result.outcomes[0].status == "aligned"
    grid = praat_textgrid.openTextgrid(str(tmp_path / "output/unknown/unknown.TextGrid"), includeEmptyIntervals=True)
    assert "??" in [row.label for row in grid.getTier("phone_tone").entries]
    mora = json.loads((tmp_path / "output/unknown/mora.json").read_text())
    assert mora["unknown_tone_indices"] == {"0": "malformed_output_exact_reading"}
    for name in ("alignment.json", "postprocess.json"):
        report = json.loads((tmp_path / "output/unknown" / name).read_text())
        assert report["tone_source"] == "tdmelodic_predicted_with_explicit_unknown"
        assert report["unknown_tone_phone_count"] > 0
        if name == "alignment.json":
            assert report["tone_encoding"] == "HH_LL_HL_LH_??"


def test_mfa_failure_isolated_from_valid_item(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    _write_audio(corpus, "bad")
    _write_audio(corpus, "good")

    result = _pipeline(mfa=FakeMfa(fail_for="bad")).run(corpus, tmp_path / "output", None)

    assert [outcome.status for outcome in result.outcomes] == ["failed", "aligned"]
    assert result.outcomes[0].reason_code == "command_failed"


def test_frontend_cache_keeps_occurrence_specific_reading_overrides_isolated(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    _write_audio(corpus, "first")
    _write_audio(corpus, "second")
    overrides = tmp_path / "overrides.yaml"
    overrides.write_text(
        """utterances:
  first:
    readings:
      - span: [0, 2]
        surface: 今日
        kana: キョウ
  second:
    readings:
      - span: [0, 2]
        surface: 今日
        kana: キョオ
""",
        encoding="utf-8",
    )

    pipeline = _pipeline(accent=EchoAccent(), g2p=OccurrenceG2p(), mfa=OccurrenceMfa())
    result = pipeline.run(corpus, tmp_path / "output", overrides)

    assert [outcome.status for outcome in result.outcomes] == ["aligned", "aligned"]
    first = (tmp_path / "output" / "first" / "frontend.json").read_text(encoding="utf-8")
    second = (tmp_path / "output" / "second" / "frontend.json").read_text(encoding="utf-8")
    assert '"kana": "キョウは晴れ"' in first
    assert '"kana": "キョオは晴れ"' in second


def test_qwen_timestamps_reach_asr_receipt_before_mfa(tmp_path: Path) -> None:
    from japanmfa.asr.qwen3 import ASRResult, Timestamp

    class TimedAsr(FakeAsr):
        def transcribe(self, paths, *, reference_texts=None):
            assert reference_texts == {paths[0]: "今日は、晴れ。"}
            return {paths[0]: ASRResult(
                paths[0], "Japanese", "今日は晴れ", "fake",
                "Qwen/Qwen3-ForcedAligner-0.6B", "今日は、晴れ。",
                (Timestamp("今日は", 0.1, 0.5), Timestamp("晴れ", 0.7, 1.0)),
                (Timestamp("、", 0.5, 0.7, "lexical_gap"), Timestamp("。", 1.0, 1.0, "boundary_point")),
            )}

    corpus = tmp_path / "corpus"
    _write_audio(corpus, "timed", "今日は、晴れ。")
    result = _pipeline(asr=TimedAsr()).run(corpus, tmp_path / "output", None)

    # This fixture's frontend supplies only 今日; the timestamped source also
    # contains は晴れ, so MFA must reject the incomplete locked token stream.
    assert result.outcomes[0].status == "failed"
    assert result.outcomes[0].reason_code == "timestamp_text_mismatch"
    artifact = tmp_path / "output" / "timed"
    asr_receipt = json.loads((artifact / "asr.json").read_text(encoding="utf-8"))
    assert asr_receipt["punctuation_timestamps"][0] == {
        "text": "、", "start": 0.5, "end": 0.7, "source": "lexical_gap"
    }
    assert (artifact / "mfa" / "corpus" / "timed.lab").read_text(encoding="utf-8") == "jmfa_000000\n"
    assert (artifact / "mfa" / "corpus" / "timed.wav").is_file()
    assert (artifact / "mfa" / "dictionary.dict").is_file()


def test_main_pipeline_checks_qwen_timing_against_locked_mfa_text(tmp_path: Path) -> None:
    from japanmfa.asr.qwen3 import ASRResult, Timestamp

    class MismatchedTimedAsr(FakeAsr):
        def transcribe(self, paths: list[Path], *, reference_texts=None) -> dict[Path, object]:
            return {path: ASRResult(path, "Japanese", "今日は晴れ", "fake",
                                    "fake-aligner", "今日は晴れ",
                                    (Timestamp("世間", 0.1, 0.8),)) for path in paths}

    corpus = tmp_path / "corpus"
    _write_audio(corpus, "timed")

    result = _pipeline(asr=MismatchedTimedAsr()).run(corpus, tmp_path / "output", None)

    assert result.outcomes[0].status == "failed"
    assert result.outcomes[0].reason_code == "timestamp_text_mismatch"


def test_native_qwen_crop_keeps_speech_outside_timestamp_anchor(tmp_path: Path) -> None:
    from japanmfa.asr.qwen3 import ASRResult, Timestamp

    class TimedAsr(FakeAsr):
        def transcribe(self, paths, *, reference_texts=None):
            return {paths[0]: ASRResult(
                paths[0], "Japanese", "今日", "fake",
                "Qwen/Qwen3-ForcedAligner-0.6B", "今日",
                (Timestamp("今日", 0.2, 0.8),),
            )}

    class RecordingMfa(FakeMfa):
        frames = 0

        def align(self, corpus_dir, dictionary, output_dir, work_dir):
            with wave.open(str(next(corpus_dir.glob("*.wav"))), "rb") as audio:
                self.frames = audio.getnframes()
            return super().align(corpus_dir, dictionary, output_dir, work_dir)

    corpus = tmp_path / "corpus"
    _write_audio(corpus, "single", "今日")
    mfa = RecordingMfa()

    _pipeline(asr=TimedAsr(), mfa=mfa).run(corpus, tmp_path / "output", None)

    assert mfa.frames == 16000
