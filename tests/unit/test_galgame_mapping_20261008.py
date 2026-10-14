"""Real G2P variants that must preserve one interval per original phone."""

from pathlib import Path

import pytest

from japanmfa.domain import Mora
from japanmfa.errors import StageFailure
from japanmfa.mfa.phone_map import PhoneMap
from japanmfa.projection import _match_morae_to_phones, labels_for_phone


MAP = Path(__file__).resolve().parents[2] / "src/japanmfa/mfa/data/japanese_mfa_v3_phone_map.yaml"


@pytest.mark.parametrize(
    "kana,phones,owners",
    [
        (["ティ"], ["tʲ", "i"], [[0], [0]]),
        (["ファ"], ["ɸ", "a"], [[0], [0]]),
        (["ソ", "ー"], ["s", "oː"], [[0], [0, 1]]),
        (["ッ", "シ"], ["ɕː", "i"], [[0, 1], [1]]),
        (["ッ", "ド"], ["dː", "o"], [[0, 1], [1]]),
    ],
)
def test_observed_variant_keeps_each_phone_whole(kana, phones, owners):
    morae = tuple(Mora(0, index, item, "H") for index, item in enumerate(kana))
    mapping = _match_morae_to_phones(morae, tuple(phones), PhoneMap.load(MAP))
    assert len(mapping) == len(phones)
    assert [[mora.index_in_token for mora in group] for group in mapping] == owners
    assert {mora.index_in_token for group in mapping for mora in group} == set(range(len(kana)))
    for group in mapping:
        labels_for_phone(group)


@pytest.mark.parametrize(
    "kana,phones",
    [
        (["ウ"], ["oː"]),
        (["ロ"], ["ɾ", "oː"]),
        (["セ", "ッ", "カ", "ク"], ["s", "e", "k", "a", "k", "ɯ"]),
        (["ス", "ッ", "ゴ", "イ"], ["s", "ɨ", "pː", "ɡ", "o", "i"]),
        (["チャ"], ["tɕ", "a", "a"]),
    ],
)
def test_missing_or_misplaced_phone_is_not_invented(kana, phones):
    morae = tuple(Mora(0, index, item, "H") for index, item in enumerate(kana))
    with pytest.raises(StageFailure):
        _match_morae_to_phones(morae, tuple(phones), PhoneMap.load(MAP))
