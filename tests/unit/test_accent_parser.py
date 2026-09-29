from __future__ import annotations

import pytest

from japanmfa.accent.parser import parse_accent
from japanmfa.domain import Mora
from japanmfa.errors import StageFailure


def locked(*kana: str) -> tuple[Mora, ...]:
    return tuple(Mora(4, index, value) for index, value in enumerate(kana))


def tones(marked: str, *kana: str) -> list[str]:
    return [m.tone for m in parse_accent(marked, locked(*kana))]  # type: ignore[list-item]


def test_parse_accent_assigns_one_tone_per_mora_at_events() -> None:
    result = parse_accent("キ[カイガ]クシュー", locked("キ", "カ", "イ", "ガ", "ク", "シュ", "ー"))

    assert [m.kana for m in result] == ["キ", "カ", "イ", "ガ", "ク", "シュ", "ー"]
    assert [m.tone for m in result] == ["L", "H", "H", "H", "L", "L", "L"]
    assert all(m.tone in {"H", "L"} for m in result)


def test_parse_accent_allows_initial_high_fall_and_final_high_run() -> None:
    assert tones("カ]イ", "カ", "イ") == ["H", "L"]
    assert tones("カ[イ", "カ", "イ") == ["L", "H"]


def test_parse_accent_allows_trailing_fall_after_single_mora() -> None:
    assert tones("ト]", "ト") == ["H"]


def test_parse_accent_allows_trailing_fall_after_final_high_mora() -> None:
    assert tones("タ[チ]", "タ", "チ") == ["L", "H"]


def test_parse_accent_rejects_trailing_rise_without_a_following_mora() -> None:
    with pytest.raises(StageFailure) as exc_info:
        parse_accent("ト[", locked("ト"))

    assert exc_info.value.reason_code == "malformed_output"


@pytest.mark.parametrize(
    "marked",
    [
        "]カイ",  # an event cannot precede the first mora
        "カ[イ[ガ",  # two rises without a fall
        "カ[[イ",  # nested / repeated event at one boundary
        "カ]",  # an event after a low run has no valid transition
        "カ]イ]ガ",  # repeated fall inside the word
    ],
)
def test_parse_accent_rejects_impossible_or_unmatched_events(marked: str) -> None:
    with pytest.raises(StageFailure) as exc_info:
        parse_accent(marked, locked("カ", "イ", "ガ"))

    assert exc_info.value.stage == "accent"


def test_parse_accent_rejects_marker_inside_mora_digraph() -> None:
    with pytest.raises(StageFailure, match="boundary"):
        parse_accent("キ[ョウ", locked("キョ", "ウ"))


def test_parse_accent_rejects_reading_mismatch_after_kana_normalization() -> None:
    with pytest.raises(StageFailure) as exc_info:
        parse_accent("キョオ", locked("キョ", "ウ"))

    assert exc_info.value.reason_code == "reading_mismatch"


def test_parse_accent_accepts_hiragana_marked_output_when_reading_matches() -> None:
    result = parse_accent("きょ[う", locked("キョ", "ウ"))

    assert [m.tone for m in result] == ["L", "H"]


def test_parse_accent_ignores_redundant_terminal_fall_after_low_mora() -> None:
    # Pinned tdmelodic returns ネ]ツ] for 0922jap 0090 熱.
    assert tones("ネ]ツ]", "ネ", "ツ") == ["H", "L"]
