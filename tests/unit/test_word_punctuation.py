from pathlib import Path

import pytest
from praatio import textgrid

from japanmfa.domain import Mora, PhoneAnnotation, PhoneInterval, Token
from japanmfa.mfa.textgrid import MfaWord
from japanmfa.output.textgrid import build_word_intervals, merge_internal_sp0_backward, publication_internal_ellipsis, publication_terminal_text, validate_five_tier_textgrid, write_five_tier_textgrid


def test_internal_sp1_is_ellipsis_in_text_and_four_timed_tiers(tmp_path: Path) -> None:
    source, kana = "ご飯食べ。", "ゴハンタベ。"
    tokens = (Token(0, 0, 2, "ご飯", ("名詞",), "ゴハン", "sudachi"),
              Token(1, 2, 4, "食べ", ("動詞",), "タベ", "sudachi"))
    aligned = (MfaWord("jmfa_000000", .2, .5), MfaWord("jmfa_000001", .71, 1.))
    annotations = (PhoneAnnotation(PhoneInterval(.2, .5, "ɴ"), 0, (), "ン", "HH", False),
                   PhoneAnnotation(PhoneInterval(.71, 1., "t"), 1, (), "タ", "LL", False))
    words, _ = build_word_intervals(1.3, source, tokens, aligned,
                                    ("jmfa_000000", "jmfa_000001"), phone_annotations=annotations)
    assert words[2] == (.5, .71, "<sp1>")
    published_source, published_kana, published_words, ledger = publication_internal_ellipsis(
        source, kana, tokens, words,
    )
    assert (published_source, published_kana) == ("ご飯……食べ。", "ゴハン……タベ。")
    assert published_words[2] == (.5, .71, "……")
    assert ledger == ({"start": .5, "end": .71, "left_lexical_ordinal": 0,
                       "right_lexical_ordinal": 1, "prior_label": "<sp1>", "mark": "……"},)
    path = tmp_path / "ellipsis.TextGrid"
    write_five_tier_textgrid(path, 1.3, published_source, published_kana, annotations, words=published_words)
    validate_five_tier_textgrid(path, 1.3, frozenset())
    grid = textgrid.openTextgrid(str(path), includeEmptyIntervals=True)
    for name in ("words", "phones", "phone_kana", "phone_tone"):
        assert [(r.start, r.end, r.label) for r in grid.getTier(name).entries if r.label == "……"] == [(.5, .71, "……")]


def test_existing_punctuation_and_edge_pauses_are_not_replaced_by_ellipsis() -> None:
    source, kana = "ご飯、食べ。", "ゴハン、タベ。"
    tokens = (Token(0, 0, 2, "ご飯", ("名詞",), "ゴハン", "sudachi"),
              Token(1, 3, 5, "食べ", ("動詞",), "タベ", "sudachi"))
    words = ((0., .2, "<sp1>"), (.2, .5, "ご飯"), (.5, .71, "、"),
             (.71, 1., "食べ"), (1., 1.3, "。"))
    assert publication_internal_ellipsis(source, kana, tokens, words) == (source, kana, words, ())


@pytest.mark.parametrize(("pause_end", "label"), ((.71, "<sp1>"), (1.3, "<sp2>"), (2.1, "<sp3>")))
def test_all_internal_long_pause_grades_become_ellipsis(pause_end: float, label: str) -> None:
    tokens = (Token(0, 0, 2, "ご飯", ("名詞",), "ゴハン", "sudachi"),
              Token(1, 2, 4, "食べ", ("動詞",), "タベ", "sudachi"))
    words = ((0., .2, "<sp1>"), (.2, .5, "ご飯"), (.5, pause_end, label),
             (pause_end, pause_end + .3, "食べ"), (pause_end + .3, pause_end + .6, "。"))
    original, kana, revised, ledger = publication_internal_ellipsis(
        "ご飯食べ。", "ゴハンタベ。", tokens, words,
    )
    assert (original, kana) == ("ご飯……食べ。", "ゴハン……タベ。")
    assert revised[2] == (.5, pause_end, "……")
    assert ledger[0]["prior_label"] == label


def test_repeated_word_occurrences_get_ellipsis_at_their_own_gaps() -> None:
    tokens = (Token(0, 0, 2, "ご飯", ("名詞",), "ゴハン", "sudachi"),
              Token(1, 2, 4, "食べ", ("動詞",), "タベ", "sudachi"),
              Token(2, 4, 6, "ご飯", ("名詞",), "ゴハン", "sudachi"))
    words = ((0., .2, "<sp1>"), (.2, .5, "ご飯"), (.5, .8, "<sp1>"),
             (.8, 1.1, "食べ"), (1.1, 1.8, "<sp2>"), (1.8, 2.1, "ご飯"))
    original, kana, revised, ledger = publication_internal_ellipsis(
        "ご飯食べご飯", "ゴハンタベゴハン", tokens, words,
    )
    assert (original, kana) == ("ご飯……食べ……ご飯", "ゴハン……タベ……ゴハン")
    assert [row[2] for row in revised] == ["<sp1>", "ご飯", "……", "食べ", "……", "ご飯"]
    assert len(ledger) == 2


def test_unpunctuated_source_uses_final_acoustic_pause_for_period_on_every_tier(tmp_path: Path) -> None:
    source, kana = "ううん。おなか空いてない", "ウウン。オナカスイテナイ"
    tokens = (Token(0, 4, len(source), "おなか空いてない", ("名詞",), "オナカスイテナイ", "sudachi"),)
    aligned = (MfaWord("jmfa_000000", .5, 1.),)
    annotations = (PhoneAnnotation(PhoneInterval(.5, 1., "a"), 0, (), "ア", "HH", False),)
    raw_words, _ = build_word_intervals(1.5, source, tokens, aligned, ("jmfa_000000",))
    assert raw_words[-1] == (1., 1.5, "<sp2>")

    published_source, published_kana, mark = publication_terminal_text(source, kana, raw_words)
    assert (published_source, published_kana, mark) == (source + "。", kana + "。", "。")
    words, unplaced = build_word_intervals(1.5, published_source, tokens, aligned, ("jmfa_000000",))
    assert unplaced == ()
    assert words[-1] == (1., 1.5, "。")
    path = tmp_path / "final.TextGrid"
    write_five_tier_textgrid(path, 1.5, published_source, published_kana, annotations, words=words)
    validate_five_tier_textgrid(path, 1.5, frozenset())
    grid = textgrid.openTextgrid(str(path), includeEmptyIntervals=True)
    for name in ("original", "kana", "words", "phones", "phone_kana", "phone_tone"):
        assert grid.getTier(name).entries[-1].label.endswith("。")
    for name in ("words", "phones", "phone_kana", "phone_tone"):
        assert (grid.getTier(name).entries[-1].start, grid.getTier(name).entries[-1].end) == (1., 1.5)


def test_existing_terminal_punctuation_is_not_replaced() -> None:
    words = ((0., .5, "あ"), (.5, 1., "？"))
    assert publication_terminal_text("あ？", "ア？", words) == ("あ？", "ア？", "")


def test_internal_sp0_extends_previous_word_and_phone_on_all_tiers(tmp_path: Path) -> None:
    source = "も作ろう。"
    tokens = (Token(0, 0, 1, "も", ("助詞",), "モ", "sudachi"),
              Token(1, 1, 4, "作ろう", ("動詞",), "ツクロウ", "sudachi"))
    aligned = (MfaWord("jmfa_000000", .2, .5), MfaWord("jmfa_000001", .57, .9))
    annotations = (PhoneAnnotation(PhoneInterval(.2, .5, "o"), 0, (), "モ", "HH", False),
                   PhoneAnnotation(PhoneInterval(.57, .9, "ts"), 1, (), "ツ", "LL", False))
    aliases = ("jmfa_000000", "jmfa_000001")
    words, _ = build_word_intervals(1.2, source, tokens, aligned, aliases, phone_annotations=annotations)
    assert (words[2]) == (.5, .57, "<sp0>")
    merged, ledger = merge_internal_sp0_backward(1.2, annotations, words)
    assert ledger == ({"start": .5, "end": .57, "previous_phone": "o", "token_index": 0},)
    words, _ = build_word_intervals(1.2, source, tokens, aligned, aliases, phone_annotations=merged)
    assert words[1:3] == ((.2, .57, "も"), (.57, .9, "作ろう"))
    path = tmp_path / "merged.TextGrid"
    write_five_tier_textgrid(path, 1.2, source, "モツクロウ。", merged, words=words)
    validate_five_tier_textgrid(path, 1.2, frozenset())
    grid = textgrid.openTextgrid(str(path), includeEmptyIntervals=True)
    for name in ("words", "phones", "phone_kana", "phone_tone"):
        entries = grid.getTier(name).entries
        assert all(entry.label != "<sp0>" for entry in entries)
        assert (entries[1].start, entries[1].end) == (.2, .57)


def test_internal_punctuation_is_not_absorbed_as_sp0() -> None:
    words = ((0., .5, "も"), (.5, .57, "、"), (.57, 1., "作ろう"))
    annotations = (PhoneAnnotation(PhoneInterval(0., .5, "o"), 0, (), "モ", "HH", False),
                   PhoneAnnotation(PhoneInterval(.57, 1., "ts"), 1, (), "ツ", "LL", False))
    merged, ledger = merge_internal_sp0_backward(1., annotations, words)
    assert ledger == ()
    assert merged[0].interval.end == .5


def test_short_pause_inside_a_word_also_extends_previous_phone() -> None:
    words = ((0., .2, "<sp1>"), (.2, .9, "こと"), (.9, 1.2, "。"))
    annotations = (PhoneAnnotation(PhoneInterval(.2, .5, "k"), 0, (), "コ", "HH", False),
                   PhoneAnnotation(PhoneInterval(.57, .9, "t"), 0, (), "ト", "HH", False))
    merged, ledger = merge_internal_sp0_backward(1.2, annotations, words)
    assert ledger == ({"start": .5, "end": .57, "previous_phone": "k", "token_index": 0},)
    assert [(row.interval.start, row.interval.end, row.interval.label) for row in merged] == [
        (0., .2, "<sp1>"), (.2, .57, "k"), (.57, .9, "t"), (.9, 1.2, "。")]


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
    for name in ("phones", "phone_kana", "phone_tone"):
        assert [entry.label for entry in grid.getTier(name).entries][::2] == ["<sp1>", "、", "？"]


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


def test_words_follow_refined_phone_silence_boundary() -> None:
    source = "ない。"
    tokens = (Token(0, 0, 2, "ない", ("形容詞",), "ナイ", "sudachi"),)
    words = (MfaWord("jmfa_000000", .5, .9),)
    annotations = (
        PhoneAnnotation(PhoneInterval(0., .5, "<sp1>"), None, (), "", "", True),
        PhoneAnnotation(PhoneInterval(.5, 1.2, "i"), 0,
                        (Mora(0, 0, "イ", "H"),), "イ", "HH", False),
        PhoneAnnotation(PhoneInterval(1.2, 1.5, "<sp1>"), None, (), "", "", True),
    )
    rows, unplaced = build_word_intervals(
        1.5, source, tokens, words, ("jmfa_000000",), phone_annotations=annotations,
    )
    assert rows == ((0., .5, "<sp1>"), (.5, 1.2, "ない"), (1.2, 1.5, "。"))
    assert unplaced == ()


def test_fragmented_pause_is_one_shared_punctuation_owner(tmp_path: Path) -> None:
    annotations = (
        PhoneAnnotation(PhoneInterval(.2, .5, "a"), 0, (), "ア", "HH", False),
        PhoneAnnotation(PhoneInterval(.5, .53, ""), None, (), "", "", True),
        PhoneAnnotation(PhoneInterval(.9, 1., ""), None, (), "", "", True),
        PhoneAnnotation(PhoneInterval(1., 1.2, "e"), 1, (), "エ", "LL", False),
        PhoneAnnotation(PhoneInterval(1.2, 1.23, ""), None, (), "", "", True),
    )
    words = ((0., .2, "<sp1>"), (.2, .5, "あ"), (.5, 1., "。"),
             (1., 1.2, "え"), (1.2, 1.8, "<sp2>"))
    path = tmp_path / "fragmented.TextGrid"
    write_five_tier_textgrid(path, 1.8, "あ。え", "ア。エ", annotations, words=words)
    grid = textgrid.openTextgrid(str(path), includeEmptyIntervals=True)
    for name in ("phones", "phone_kana", "phone_tone"):
        entries = grid.getTier(name).entries
        assert [(r.start, r.end, r.label) for r in entries if r.label in {"。", "<sp1>", "<sp2>"}] == [
            (0., .2, "<sp1>"), (.5, 1., "。"), (1.2, 1.8, "<sp2>")]
        assert len(entries) == 5


def test_validator_rejects_punctuation_mismatch(tmp_path: Path) -> None:
    import pytest
    from japanmfa.output.textgrid import _render
    tiers = (("original", (("0.0", "1.0", "あ。"),)),
             ("kana", (("0.0", "1.0", "ア。"),)),
             ("words", (("0.0", "0.5", "あ"), ("0.5", "1.0", "。"))),
             ("phones", (("0.0", "0.5", "a"), ("0.5", "1.0", "<sp2>"))),
             ("phone_kana", (("0.0", "0.5", "ア"), ("0.5", "1.0", "<sp2>"))),
             ("phone_tone", (("0.0", "0.5", "HH"), ("0.5", "1.0", "<sp2>"))))
    path = tmp_path / "mismatch.TextGrid"
    path.write_text(_render(1., tiers))
    with pytest.raises(ValueError, match="punctuation|pause"):
        validate_five_tier_textgrid(path, 1., frozenset())


def test_punctuation_cannot_overwrite_speech(tmp_path: Path) -> None:
    import pytest
    annotations = (PhoneAnnotation(PhoneInterval(0., 1., "a"), 0, (), "ア", "HH", False),)
    path = tmp_path / "overlap.TextGrid"
    with pytest.raises(ValueError, match="punctuation|pause"):
        write_five_tier_textgrid(path, 1., "あ。", "ア。", annotations,
                                words=((0., .5, "あ"), (.5, 1., "。")))
    assert not path.exists()


def test_publication_json_rows_use_same_merged_pause_labels(tmp_path: Path) -> None:
    from japanmfa.output.textgrid import publication_phone_partition
    annotations = (PhoneAnnotation(PhoneInterval(.2, .5, "a"), 0, (), "ア", "HH", False),
                   PhoneAnnotation(PhoneInterval(.5, .53, ""), None, (), "", "", True))
    words = ((0., .2, "<sp1>"), (.2, .5, "あ"), (.5, 1., "。"))
    published = publication_phone_partition(1., annotations, words=words)
    assert [(a.interval.start, a.interval.end, a.interval.label) for a in published] == [
        (0., .2, "<sp1>"), (.2, .5, "a"), (.5, 1., "。")]
    assert publication_phone_partition(1., published, words=words) == published
