from pathlib import Path

import pytest

from japanmfa.domain import Token
from japanmfa.errors import StageFailure
from japanmfa.frontend.overrides import (
    ReadingOverrideSet,
    apply_reading_overrides,
    load_reading_overrides,
)


def token(index: int, start: int, end: int, surface: str, reading: str = "キョウ") -> Token:
    return Token(index, start, end, surface, ("名詞",), reading, "sudachi")


def write_yaml(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "readings.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_valid_override_changes_only_selected_occurrence(tmp_path: Path) -> None:
    overrides = load_reading_overrides(
        write_yaml(
            tmp_path,
            """utterances:
  u1:
    readings:
      - span: [0, 2]
        surface: 今日
        kana: コンニチ
""",
        )
    )
    tokens = (token(0, 0, 2, "今日"), token(1, 2, 3, "は"), token(2, 3, 5, "今日"))
    changed = apply_reading_overrides("u1", "今日は今日", tokens, overrides)
    assert changed[0].reading == "コンニチ"
    assert changed[0].reading_source == "override"
    assert changed[2].reading == "キョウ"
    assert changed[2].reading_source == "sudachi"


def test_override_uses_original_character_coordinates_with_linebreaks(tmp_path: Path) -> None:
    original = " \r\n今日は\r\n晴れ  \r\n"
    overrides = load_reading_overrides(
        write_yaml(
            tmp_path,
            """utterances:
  u1:
    readings:
      - span: [3, 5]
        surface: 今日
        kana: コンニチ
""",
        )
    )
    tokens = (token(0, 0, 2, "今日"), token(1, 2, 3, "は"), token(2, 3, 5, "晴れ"))
    changed = apply_reading_overrides("u1", original, tokens, overrides)
    assert changed[0].reading == "コンニチ"
    assert changed[0].reading_source == "override"
    assert changed[1].reading == "キョウ"


def test_override_fails_when_original_cannot_reproduce_processing_tokens(tmp_path: Path) -> None:
    overrides = load_reading_overrides(
        write_yaml(
            tmp_path,
            """utterances:
  u1:
    readings:
      - span: [0, 2]
        surface: 今日
        kana: コンニチ
""",
        )
    )
    tokens = (token(0, 0, 2, "今日"),)
    with pytest.raises(StageFailure) as exc_info:
        apply_reading_overrides("u1", "明日", tokens, overrides)
    assert exc_info.value.reason_code == "token_span_mismatch"


def test_override_set_can_be_empty() -> None:
    tokens = (token(0, 0, 2, "今日"),)
    assert apply_reading_overrides("missing", "今日", tokens, ReadingOverrideSet({})) == tokens


@pytest.mark.parametrize(
    ("yaml_text", "reason"),
    [
        (
            """utterances:\n  u1:\n    readings:\n      - span: [-1, 2]\n        surface: 今日\n        kana: キョウ\n""",
            "invalid_override",
        ),
        (
            """utterances:\n  u1:\n    readings:\n      - span: [0, 2]\n        surface: 明日\n        kana: アシタ\n""",
            "override_surface_mismatch",
        ),
        (
            """utterances:\n  u1:\n    readings:\n      - span: [0, 2]\n        surface: 今日\n        kana: コンニチ\n      - span: [1, 3]\n        surface: 日は\n        kana: ニチハ\n""",
            "overlapping_overrides",
        ),
    ],
)
def test_invalid_override_is_rejected_before_application(
    tmp_path: Path, yaml_text: str, reason: str
) -> None:
    overrides = load_reading_overrides(write_yaml(tmp_path, yaml_text))
    tokens = (token(0, 0, 2, "今日"), token(1, 2, 3, "は"))
    with pytest.raises(StageFailure) as exc_info:
        apply_reading_overrides("u1", "今日は", tokens, overrides)
    assert exc_info.value.reason_code == reason
    assert [item.reading for item in tokens] == ["キョウ", "キョウ"]


def test_duplicate_entries_are_rejected(tmp_path: Path) -> None:
    overrides = load_reading_overrides(
        write_yaml(
            tmp_path,
            """utterances:
  u1:
    readings:
      - span: [0, 2]
        surface: 今日
        kana: キョウ
      - span: [0, 2]
        surface: 今日
        kana: コンニチ
""",
        )
    )
    with pytest.raises(StageFailure, match="duplicate"):
        apply_reading_overrides("u1", "今日", (token(0, 0, 2, "今日"),), overrides)


def test_invalid_kana_is_rejected_while_loading(tmp_path: Path) -> None:
    overrides = load_reading_overrides(
        write_yaml(
            tmp_path,
            """utterances:
  u1:
    readings:
      - span: [0, 2]
        surface: 今日
        kana: today
""",
        )
    )
    with pytest.raises(StageFailure) as exc_info:
        apply_reading_overrides("u1", "今日", (token(0, 0, 2, "今日"),), overrides)
    assert exc_info.value.reason_code == "invalid_override_kana"


def test_override_must_cover_one_complete_token(tmp_path: Path) -> None:
    overrides = load_reading_overrides(
        write_yaml(
            tmp_path,
            """utterances:
  u1:
    readings:
      - span: [0, 1]
        surface: 今
        kana: イマ
""",
        )
    )
    with pytest.raises(StageFailure, match="complete token"):
        apply_reading_overrides("u1", "今日", (token(0, 0, 2, "今日"),), overrides)


def test_override_file_must_have_expected_yaml_shape(tmp_path: Path) -> None:
    path = write_yaml(tmp_path, "utterances: []\n")
    with pytest.raises(StageFailure, match="utterances"):
        load_reading_overrides(path)
