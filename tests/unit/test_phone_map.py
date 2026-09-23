from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from japanmfa.errors import StageFailure
from japanmfa.mfa.phone_map import PhoneMap


DATA_PATH = Path(__file__).parents[2] / "src" / "japanmfa" / "mfa" / "data" / "japanese_mfa_v3_phone_map.yaml"


def test_bundled_phone_map_is_versioned_and_matches_observed_groups() -> None:
    phone_map = PhoneMap.load(DATA_PATH)

    assert phone_map.model_family == "japanese_mfa_v3"
    assert phone_map.normalize("ɴ") == "N"
    assert phone_map.rule_for(("オ", "ー"), ("oː",)).kana == ("オ", "ー")


def test_bundled_long_vowel_sequence_declares_per_phone_mora_spans() -> None:
    phone_map = PhoneMap.load(DATA_PATH)

    assert phone_map.rule_for(("オ", "ー"), ("o", "o")).mora_spans == (
        (0, 1),
        (1, 2),
    )


def test_phone_map_rejects_model_family_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "map.yaml"
    path.write_text(
        "model_family: another_model\nnormalizations: {}\nrules: []\n",
        encoding="utf-8",
    )

    with pytest.raises(StageFailure) as exc_info:
        PhoneMap.load(path)

    assert (exc_info.value.stage, exc_info.value.reason_code) == (
        "projection",
        "model_family_mismatch",
    )


def test_phone_map_model_family_cannot_be_overridden(tmp_path: Path) -> None:
    path = tmp_path / "map.yaml"
    path.write_text(
        "model_family: another_model\nnormalizations: {}\nrules:\n  - kana: [ア]\n    phones: [a]\n",
        encoding="utf-8",
    )

    with pytest.raises(TypeError):
        PhoneMap.load(path, model_family="another_model")


def test_phone_map_rejects_duplicate_rules_and_unknown_fields(tmp_path: Path) -> None:
    path = tmp_path / "map.yaml"
    path.write_text(
        """
model_family: japanese_mfa_v3
normalizations: {}
rules:
  - kana: [ア]
    phones: [a]
    extra: forbidden
  - kana: [ア]
    phones: [a]
""",
        encoding="utf-8",
    )

    with pytest.raises(StageFailure) as exc_info:
        PhoneMap.load(path)

    assert exc_info.value.reason_code == "unknown_rule_field"

    path.write_text(
        """
model_family: japanese_mfa_v3
normalizations: {}
rules:
  - kana: [ア]
    phones: [a]
  - kana: [ア]
    phones: [a]
""",
        encoding="utf-8",
    )
    with pytest.raises(StageFailure) as exc_info:
        PhoneMap.load(path)
    assert exc_info.value.reason_code == "duplicate_rule"


@pytest.mark.parametrize(
    "rules, normalizations",
    [
        (
            """
  - kana: [ア]
    phones: [a]
    cost: 0
  - kana: [ア]
    phones: [a]
    cost: 2
""",
            "{}",
        ),
        (
            """
  - kana: [ア]
    phones: [ɴ]
  - kana: [ア]
    phones: [N]
""",
            "ɴ: N",
        ),
    ],
)
def test_phone_map_rejects_semantically_duplicate_rules(
    tmp_path: Path, rules: str, normalizations: str
) -> None:
    path = tmp_path / "map.yaml"
    path.write_text(
        f"model_family: japanese_mfa_v3\nnormalizations:\n  {normalizations}\nrules:\n{rules}",
        encoding="utf-8",
    )

    with pytest.raises(StageFailure) as exc_info:
        PhoneMap.load(path)

    assert exc_info.value.reason_code == "duplicate_rule"


def test_phone_map_rejects_unknown_top_level_fields(tmp_path: Path) -> None:
    path = tmp_path / "map.yaml"
    path.write_text(
        "model_family: japanese_mfa_v3\nnormalizations: {}\nrules: []\nunknown: true\n",
        encoding="utf-8",
    )

    with pytest.raises(StageFailure) as exc_info:
        PhoneMap.load(path)

    assert exc_info.value.reason_code == "unknown_field"


def test_phone_map_requires_spans_for_unequal_multi_mora_multi_phone_rules(tmp_path: Path) -> None:
    path = tmp_path / "map.yaml"
    path.write_text(
        """
model_family: japanese_mfa_v3
normalizations: {}
rules:
  - kana: [ア, イ]
    phones: [a, i, j]
""",
        encoding="utf-8",
    )

    with pytest.raises(StageFailure) as exc_info:
        PhoneMap.load(path)

    assert exc_info.value.reason_code == "invalid_rule"


def test_phone_map_accepts_explicit_spans_for_unequal_multi_mora_multi_phone_rules(
    tmp_path: Path,
) -> None:
    path = tmp_path / "map.yaml"
    path.write_text(
        """
model_family: japanese_mfa_v3
normalizations: {}
rules:
  - kana: [ア, イ]
    phones: [a, a, i]
    mora_spans: [[0, 1], [0, 1], [1, 2]]
""",
        encoding="utf-8",
    )

    rule = PhoneMap.load(path).rules[0]

    assert rule.mora_spans == ((0, 1), (0, 1), (1, 2))


@pytest.mark.parametrize(
    "spans",
    [
        "[[0, 1], [2, 3]]",
        "[[0, 3], [1, 2]]",
    ],
)
def test_phone_map_rejects_gapped_or_reverse_ordered_spans(
    tmp_path: Path, spans: str
) -> None:
    path = tmp_path / "map.yaml"
    path.write_text(
        f"""
model_family: japanese_mfa_v3
normalizations: {{}}
rules:
  - kana: [ア, イ, ウ]
    phones: [a, i]
    mora_spans: {spans}
""",
        encoding="utf-8",
    )

    with pytest.raises(StageFailure) as exc_info:
        PhoneMap.load(path)

    assert exc_info.value.reason_code == "invalid_rule"
