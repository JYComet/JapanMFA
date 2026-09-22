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


def test_phone_map_rejects_unknown_top_level_fields(tmp_path: Path) -> None:
    path = tmp_path / "map.yaml"
    path.write_text(
        "model_family: japanese_mfa_v3\nnormalizations: {}\nrules: []\nunknown: true\n",
        encoding="utf-8",
    )

    with pytest.raises(StageFailure) as exc_info:
        PhoneMap.load(path)

    assert exc_info.value.reason_code == "unknown_field"
