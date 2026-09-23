from __future__ import annotations

from pathlib import Path

import pytest

from japanmfa.errors import StageFailure
from japanmfa.mfa.textgrid import MfaAlignment, parse_mfa_textgrid


FIXTURE = Path(__file__).parents[1] / "fixtures" / "mfa" / "aligned.TextGrid"


def test_parse_mfa_textgrid_discovers_named_tiers_and_preserves_raw_boundaries() -> None:
    alignment = parse_mfa_textgrid(FIXTURE, frozenset({"", "sil", "sp", "spn"}))

    assert isinstance(alignment, MfaAlignment)
    assert [(word.alias, word.start, word.end) for word in alignment.words] == [
        ("jmfa_000000", 0.0, 1.0),
        ("jmfa_000001", 1.1, 2.0),
    ]
    assert [(phone.label, phone.start, phone.end, phone.word_alias, phone.is_silence)
            for phone in alignment.phones] == [
        ("k", 0.1, 0.2, "jmfa_000000", False),
        ("a", 0.2, 0.4, "jmfa_000000", False),
        ("sil", 0.4, 0.5, None, True),
        ("r", 1.1, 1.3, "jmfa_000001", False),
        ("e", 1.3, 1.5, "jmfa_000001", False),
        ("sp", 1.5, 1.6, None, True),
        ("spn", 2.0, 2.1, None, True),
    ]
    assert [(item.label, item.start, item.end, item.tier_name)
            for item in alignment.diagnostic_intervals] == [
        ("", 0.5, 0.5, "phones"),
        ("spn", 2.1, 2.1, "phones"),
    ]


def test_zero_duration_non_silence_phone_is_a_typed_parse_failure(tmp_path: Path) -> None:
    path = tmp_path / "zero.TextGrid"
    path.write_text(_textgrid(phone_rows=[(0.0, 1.0, "a"), (1.0, 1.0, "k")]), encoding="utf-8")

    with pytest.raises(StageFailure) as exc_info:
        parse_mfa_textgrid(path, frozenset({"sil"}))

    assert (exc_info.value.stage, exc_info.value.reason_code) == (
        "mfa_parse",
        "zero_duration_phone",
    )


def test_positive_blank_phone_intervals_survive_for_praat_boundaries(tmp_path: Path) -> None:
    path = tmp_path / "blanks.TextGrid"
    path.write_text(_textgrid(phone_rows=[(0.0, .2, ""), (.2, .5, "a"), (.5, .8, ""), (.8, 1.0, "a"), (1.0, 2.0, "")]), encoding="utf-8")
    alignment = parse_mfa_textgrid(path, frozenset({"sil"}))
    assert [(p.start, p.end, p.label, p.is_silence) for p in alignment.phones] == [
        (0.0, .2, "", True), (.2, .5, "a", False), (.5, .8, "", True), (.8, 1.0, "a", False), (1.0, 2.0, "", True),
    ]


def test_overlapping_phone_intervals_fail_without_shifting_boundaries(tmp_path: Path) -> None:
    path = tmp_path / "overlap.TextGrid"
    path.write_text(_textgrid(phone_rows=[(0.0, 0.6, "a"), (0.5, 1.0, "k")]), encoding="utf-8")

    with pytest.raises(StageFailure) as exc_info:
        parse_mfa_textgrid(path, frozenset({"sil"}))

    assert (exc_info.value.stage, exc_info.value.reason_code) == (
        "mfa_parse",
        "invalid_boundaries",
    )


def test_non_silence_phone_without_one_containing_word_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "uncontained.TextGrid"
    path.write_text(_textgrid(phone_rows=[(0.0, 1.0, "a"), (2.5, 2.6, "k")]), encoding="utf-8")

    with pytest.raises(StageFailure) as exc_info:
        parse_mfa_textgrid(path, frozenset({"sil"}))

    assert (exc_info.value.stage, exc_info.value.reason_code) == (
        "mfa_parse",
        "phone_not_contained",
    )


def test_phone_spanning_two_words_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "dual-contained.TextGrid"
    path.write_text(
        _textgrid(phone_rows=[(0.0, 2.0, "a")]).replace(
            'xmax = 2\n            text = "jmfa_000000"',
            'xmax = 1\n            text = "jmfa_000000"',
        ).replace(
            'intervals: size = 1\n        intervals [1]:\n            xmin = 0\n            xmax = 1\n            text = "jmfa_000000"',
            'intervals: size = 2\n        intervals [1]:\n            xmin = 0\n            xmax = 1\n            text = "jmfa_000000"\n        intervals [2]:\n            xmin = 1\n            xmax = 2\n            text = "jmfa_000001"',
        ),
        encoding="utf-8",
    )

    with pytest.raises(StageFailure) as exc_info:
        parse_mfa_textgrid(path, frozenset({"sil"}))

    assert (exc_info.value.stage, exc_info.value.reason_code) == (
        "mfa_parse",
        "phone_word_overlap",
    )


def _textgrid(*, phone_rows: list[tuple[float, float, str]]) -> str:
    phone_lines = []
    for index, (start, end, label) in enumerate(phone_rows, start=1):
        phone_lines.extend(
            [
                f"        intervals [{index}]:",
                f"            xmin = {start}",
                f"            xmax = {end}",
                f'            text = "{label}"',
            ]
        )
    return "\n".join(
        [
            'File type = "ooTextFile"',
            'Object class = "TextGrid"',
            "xmin = 0",
            "xmax = 2",
            "tiers? <exists>",
            "size = 2",
            "item []:",
            "    item [1]:",
            '        class = "IntervalTier"',
            '        name = "words"',
            "        xmin = 0",
            "        xmax = 2",
            "        intervals: size = 1",
            "        intervals [1]:",
            "            xmin = 0",
            "            xmax = 2",
            '            text = "jmfa_000000"',
            "    item [2]:",
            '        class = "IntervalTier"',
            '        name = "phones"',
            "        xmin = 0",
            "        xmax = 2",
            f"        intervals: size = {len(phone_rows)}",
            *phone_lines,
            "",
        ]
    )
