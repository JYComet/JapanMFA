from __future__ import annotations

import pytest

from japanmfa.domain import Token
from japanmfa.frontend.mora import segment_morae


def token(kana: str) -> Token:
    return Token(0, 0, 1, kana, ("名詞",), kana, "sudachi")


@pytest.mark.parametrize(
    ("kana", "expected"),
    [
        ("キョウ", ["キョ", "ウ"]),
        ("ガッコウ", ["ガ", "ッ", "コ", "ウ"]),
        ("コンピューター", ["コ", "ン", "ピュ", "ー", "タ", "ー"]),
        ("ファイル", ["ファ", "イ", "ル"]),
        ("ヴァイオリン", ["ヴァ", "イ", "オ", "リ", "ン"]),
    ],
)
def test_segment_morae(kana: str, expected: list[str]) -> None:
    morae = segment_morae(token(kana))

    assert [m.kana for m in morae] == expected
    assert [m.token_index for m in morae] == [0] * len(expected)
    assert [m.index_in_token for m in morae] == list(range(len(expected)))
    assert all(m.tone is None for m in morae)


@pytest.mark.parametrize("kana", ["ャキ", "ァイ", "ュ"])
def test_segment_morae_rejects_leading_combining_small_kana(kana: str) -> None:
    with pytest.raises(ValueError, match="leading combining"):
        segment_morae(token(kana))


@pytest.mark.parametrize("kana", ["キA", "キ・", "キ\N{HIRAGANA LETTER KO}"])
def test_segment_morae_rejects_unsupported_code_points(kana: str) -> None:
    with pytest.raises(ValueError, match="unsupported"):
        segment_morae(token(kana))


def test_segment_morae_rejects_combining_small_kana_after_standalone_mora() -> None:
    with pytest.raises(ValueError, match="combine"):
        segment_morae(token("ッャ"))
