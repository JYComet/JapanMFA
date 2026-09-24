from pathlib import Path

from praatio import textgrid

from japanmfa.domain import Mora, PhoneAnnotation, PhoneInterval, Token
from japanmfa.mfa.textgrid import MfaWord
from japanmfa.output.textgrid import build_word_intervals, validate_five_tier_textgrid, write_five_tier_textgrid


def test_source_punctuation_replaces_real_word_gap_silence(tmp_path: Path) -> None:
    source = "世界、大丈夫？"
    tokens = (
        Token(0, 0, 2, "世界", ("名詞",), "セカイ", "sudachi"),
        Token(1, 3, 6, "大丈夫", ("名詞",), "ダイジョウブ", "sudachi"),
    )
    words = (MfaWord("jmfa_000000", .5, 1.0), MfaWord("jmfa_000001", 1.2, 1.8))
    rows, unplaced = build_word_intervals(2.2, source, tokens, words, ("jmfa_000000", "jmfa_000001"))
    assert rows == ((0., .5, "<sp1>"), (.5, 1., "世界"), (1., 1.2, "、"), (1.2, 1.8, "大丈夫"), (1.8, 2.2, "？"))
    assert unplaced == ()

    mora = Mora(0, 0, "セ", "H")
    annotations = (
        PhoneAnnotation(PhoneInterval(.5, 1., "se"), 0, (mora,), "セ", "HH", False),
        PhoneAnnotation(PhoneInterval(1.2, 1.8, "da"), 1, (mora,), "ダ", "HH", False),
    )
    path = tmp_path / "punct.TextGrid"
    write_five_tier_textgrid(path, 2.2, "<sp1>" + source, "<sp1>セカイ、ダイジョウブ？", annotations, words=rows)
    validate_five_tier_textgrid(path, 2.2, frozenset())
    grid = textgrid.openTextgrid(str(path), includeEmptyIntervals=True)
    assert [tier.name for tier in grid.tiers] == ["original", "kana", "words", "phones", "phone_kana", "phone_tone"]
    assert [entry.label for entry in grid.getTier("words").entries] == ["<sp1>", "世界", "、", "大丈夫", "？"]
    assert [entry.label for entry in grid.getTier("phones").entries if entry.label.startswith("<sp")] == ["<sp1>", "<sp1>", "<sp1>"]


def test_punctuation_without_acoustic_gap_is_reported_without_time() -> None:
    source = "世界、大丈夫"
    tokens = (
        Token(0, 0, 2, "世界", ("名詞",), "セカイ", "sudachi"),
        Token(1, 3, 6, "大丈夫", ("名詞",), "ダイジョウブ", "sudachi"),
    )
    words = (MfaWord("jmfa_000000", 0., 1.), MfaWord("jmfa_000001", 1., 2.))
    rows, unplaced = build_word_intervals(2., source, tokens, words, ("jmfa_000000", "jmfa_000001"))
    assert rows == ((0., 1., "世界"), (1., 2., "大丈夫"))
    assert unplaced == ("、",)
