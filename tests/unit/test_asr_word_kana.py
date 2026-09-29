from __future__ import annotations

import pytest

from japanmfa.asr.qwen3 import Timestamp
from japanmfa.asr.word_kana import merge_timed_words
from japanmfa.domain import Token
from japanmfa.errors import StageFailure


def token(index: int, start: int, end: int, surface: str, reading: str) -> Token:
    return Token(index, start, end, surface, (), reading, "sudachi")


def test_full_context_readings_follow_qwen_word_times() -> None:
    words = merge_timed_words(
        "うん、お腹空いてない。",
        (
            Timestamp("うん", 0.56, 1.12),
            Timestamp("お腹", 1.84, 2.32),
            Timestamp("空い", 2.48, 2.56),
            Timestamp("て", 2.56, 2.8),
            Timestamp("ない", 2.8, 2.88),
        ),
        (
            token(0, 0, 2, "うん", "ウン"),
            token(1, 3, 5, "お腹", "オナカ"),
            token(2, 5, 7, "空い", "アイ"),
            token(3, 7, 8, "て", "テ"),
            token(4, 8, 10, "ない", "ナイ"),
        ),
    )
    assert words == [
        {"text": "うん", "kana": "ウン", "start": 0.56, "end": 1.12},
        {"text": "お腹", "kana": "オナカ", "start": 1.84, "end": 2.32},
        {"text": "空い", "kana": "アイ", "start": 2.48, "end": 2.56},
        {"text": "て", "kana": "テ", "start": 2.56, "end": 2.8},
        {"text": "ない", "kana": "ナイ", "start": 2.8, "end": 2.88},
    ]


def test_qwen_unit_spanning_two_sudachi_tokens_keeps_one_timed_word() -> None:
    words = merge_timed_words(
        "今日は。",
        (Timestamp("今日は", 0.1, 0.7),),
        (token(0, 0, 2, "今日", "キョウ"), token(1, 2, 3, "は", "ハ")),
    )
    assert words == [{"text": "今日は", "kana": "キョウハ", "start": 0.1, "end": 0.7}]


def test_qwen_units_splitting_one_sudachi_token_are_merged() -> None:
    words = merge_timed_words(
        "今日。",
        (Timestamp("今", 0.1, 0.3), Timestamp("日", 0.3, 0.5)),
        (token(0, 0, 2, "今日", "キョウ"),),
    )
    assert words == [{"text": "今日", "kana": "キョウ", "start": 0.1, "end": 0.5}]


def test_mismatched_qwen_text_fails_instead_of_guessing_kana() -> None:
    with pytest.raises(StageFailure, match="lexical"):
        merge_timed_words(
            "今日。", (Timestamp("明日", 0.1, 0.5),),
            (token(0, 0, 2, "今日", "キョウ"),),
        )


def test_native_qwen_word_can_contain_internal_punctuation() -> None:
    words = merge_timed_words(
        "うぅ～ん……",
        (Timestamp("うぅ～ん", 0.0, 1.92),),
        (token(0, 0, 2, "うぅ", "ウウ"), token(1, 3, 4, "ん", "ン")),
    )

    assert words == [{"text": "うぅ～ん", "kana": "ウウン", "start": 0.0, "end": 1.92}]
