from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from japanmfa.audio import AudioInfo
from japanmfa.config import PipelineConfig
from japanmfa.domain import Pronunciation, SourceText, Token
from japanmfa.errors import StageFailure, SkipUtterance
from japanmfa.frontend.mora import segment_morae
from japanmfa.mfa.phone_map import PhoneMap
from japanmfa.pipeline import JapanMFAPipeline


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

    def transcribe(self, paths: list[Path]) -> dict[Path, object]:
        from japanmfa.asr.qwen3 import ASRResult

        return {path: ASRResult(path, "Japanese", self.text, "fake") for path in paths}


class NonJapaneseErrorAsr:
    def transcribe(self, _paths: list[Path]) -> dict[Path, object]:
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


class ExplodingAccent:
    def predict(self, _requests: object) -> dict[int, str]:
        raise RuntimeError("OPENAI_API_KEY=super-secret-token")


class FakeG2p:
    def pronounce(self, readings: tuple[str, ...], _work_dir: Path) -> tuple[Pronunciation, ...]:
        return tuple(Pronunciation(reading, ("k", "jo", "u")) for reading in readings)


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


def _pipeline(*, accent: object | None = None, mfa: object | None = None, asr: object | None = None) -> JapanMFAPipeline:
    return JapanMFAPipeline(
        config=PipelineConfig(),
        audio_normalizer=FakeAudio(),
        asr_client=asr or FakeAsr(),
        frontend=FakeFrontend(),
        accent_client=accent or FakeAccent(),
        g2p_client=FakeG2p(),
        mfa_runner=mfa or FakeMfa(),
        phone_map=PhoneMap.load(Path(__file__).parents[2] / "src" / "japanmfa" / "mfa" / "data" / "japanese_mfa_v3_phone_map.yaml"),
    )


def _write_audio(root: Path, name: str, text: str | None = "今日は晴れ") -> None:
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{name}.wav"
    path.write_bytes(b"RIFF-fake")
    if text is not None:
        path.with_suffix(".txt").write_text(text, encoding="utf-8")


def test_fake_backends_write_valid_five_tier_and_reports(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    _write_audio(corpus, "ok")

    result = _pipeline().run(corpus, tmp_path / "output", None)

    assert result.summary["counts"] == {"aligned": 1, "failed": 0, "skipped": 0}
    artifact = tmp_path / "output" / "ok"
    assert (artifact / "ok.TextGrid").is_file()
    assert all((artifact / name).is_file() for name in ("alignment.json", "frontend.json", "asr.json", "mfa.json"))
    assert '"status": "aligned"' in (tmp_path / "output" / "manifest.jsonl").read_text()


def test_missing_text_with_non_japanese_asr_is_skipped(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    _write_audio(corpus, "missing", None)

    result = _pipeline(asr=FakeAsr("Tokyo")).run(corpus, tmp_path / "output", None)

    assert result.outcomes[0].status == "skipped"
    assert result.outcomes[0].reason_code == "unsupported_japanese_text"


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


def test_mfa_failure_isolated_from_valid_item(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    _write_audio(corpus, "bad")
    _write_audio(corpus, "good")

    result = _pipeline(mfa=FakeMfa(fail_for="bad")).run(corpus, tmp_path / "output", None)

    assert [outcome.status for outcome in result.outcomes] == ["failed", "aligned"]
    assert result.outcomes[0].reason_code == "command_failed"
