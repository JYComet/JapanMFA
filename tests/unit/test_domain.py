from pathlib import Path

import pytest

from japanmfa.domain import (
    Mora,
    PhoneAnnotation,
    PhoneInterval,
    Pronunciation,
    SourceText,
    Token,
    Utterance,
    UtteranceOutcome,
)
from japanmfa.errors import SkipUtterance, StageFailure


def test_phone_interval_rejects_non_positive_duration() -> None:
    with pytest.raises(ValueError, match="end must be greater"):
        PhoneInterval(start=1.0, end=1.0, label="a")

    with pytest.raises(ValueError, match="end must be greater"):
        PhoneInterval(start=2.0, end=1.0, label="a")


def test_domain_records_are_frozen_and_have_stable_fields() -> None:
    utterance = Utterance("u1", Path("audio.wav"), None)
    source = SourceText("今日", "今日", "txt")
    token = Token(0, 0, 2, "今日", ("名詞",), "キョウ", "sudachi")
    mora = Mora(0, 0, "キョ")
    pronunciation = Pronunciation("キョウ", ("k", "jo", "N"))
    interval = PhoneInterval(0.0, 0.1, "k")
    annotation = PhoneAnnotation(interval, 0, (mora,), "キョ", "L", False)
    outcome = UtteranceOutcome("u1", "aligned", None, None, None, {"audio": 0.1})

    assert utterance.audio_path == Path("audio.wav")
    assert source.source == "txt"
    assert token.reading_source == "sudachi"
    assert mora.tone is None
    assert pronunciation.phones == ("k", "jo", "N")
    assert annotation.interval == interval
    assert outcome.stage_durations["audio"] == 0.1

    with pytest.raises(AttributeError):
        token.reading = "ヘンコウ"  # type: ignore[misc]


def test_typed_pipeline_errors_expose_details() -> None:
    skipped = SkipUtterance("unsupported_language", "not Japanese", {"text": "hello"})
    failed = StageFailure("frontend", "invalid_reading", "bad reading", {"token": 1})

    assert skipped.reason_code == "unsupported_language"
    assert skipped.details == {"text": "hello"}
    assert failed.stage == "frontend"
    assert failed.reason_code == "invalid_reading"
    assert failed.details == {"token": 1}
