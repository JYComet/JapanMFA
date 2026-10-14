"""A pinned dictionary candidate may recover a G2P-dropped geminate."""

from pathlib import Path

import pytest

from japanmfa.domain import Pronunciation, Token
from japanmfa.errors import StageFailure
from japanmfa.frontend.mora import segment_morae
from japanmfa.mfa.phone_map import PhoneMap
from japanmfa.projection import filter_mappable_pronunciations


PHONE_MAP = PhoneMap.load(
    Path(__file__).resolve().parents[2]
    / "src/japanmfa/mfa/data/japanese_mfa_v3_phone_map.yaml"
)


def _filter(reading: str, phones: tuple[str, ...]) -> Pronunciation:
    token = Token(0, 0, len(reading), reading, (), reading, "sudachi")
    return filter_mappable_pronunciations(
        (token,), (Pronunciation(reading, phones),),
        {0: segment_morae(token)}, PHONE_MAP,
    )[0]


@pytest.mark.parametrize(
    "reading,g2p,expected",
    [
        ("オッパイ", ("o", "p", "a", "i"), ("o", "pː", "a", "i")),
        ("マッタク", ("m", "a", "t", "a", "k", "ɯ"), ("m", "a", "tː", "a", "k", "ɯ")),
        ("セッカク", ("s", "e", "k", "a", "k", "ɯ"), ("s", "e", "kː", "a", "k", "ɯ")),
        ("カッテニ", ("k", "a", "t", "e", "ɲ", "i"), ("k", "a", "tː", "e", "ɲ", "i")),
    ],
)
def test_exact_dictionary_candidate_recovers_missing_geminate(
    reading: str, g2p: tuple[str, ...], expected: tuple[str, ...]
) -> None:
    selected = _filter(reading, g2p)
    assert selected.phones == expected
    assert selected.alternates == ()


def test_existing_mappable_candidate_remains_byte_identical() -> None:
    phones = ("o", "pː", "a", "i")
    assert _filter("オッパイ", phones) == Pronunciation("オッパイ", phones)


def test_fallback_rejects_a_candidate_returned_for_another_reading() -> None:
    token = Token(0, 0, 4, "オッパイ", (), "オッパイ", "sudachi")
    wrong = Pronunciation("アッパイ", ("o", "p", "a", "i"))
    with pytest.raises(StageFailure) as error:
        filter_mappable_pronunciations(
            (token,), (wrong,), {0: segment_morae(token)}, PHONE_MAP,
        )
    assert error.value.reason_code == "no_mappable_pronunciation"


@pytest.mark.parametrize(
    "reading,phones",
    [
        ("アッパイ", ("a", "p", "a", "i")),
        ("マッタク", ("m", "a", "t", "o", "k", "ɯ")),
        ("ケッコウ", ("k", "e", "k", "oː")),
    ],
)
def test_other_missing_or_wrong_phones_remain_rejected(
    reading: str, phones: tuple[str, ...]
) -> None:
    with pytest.raises(StageFailure, match="no MFA G2P candidate") as error:
        _filter(reading, phones)
    assert error.value.reason_code == "no_mappable_pronunciation"
