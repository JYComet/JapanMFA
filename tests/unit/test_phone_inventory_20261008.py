"""Observed G2P/dictionary phones retain their original interval and mora owners."""
from pathlib import Path

import pytest

from japanmfa.domain import Mora, Token
from japanmfa.errors import StageFailure
from japanmfa.frontend.mora import segment_morae
from japanmfa.mfa.phone_map import PhoneMap
from japanmfa.projection import _match_morae_to_phones

MAP = Path(__file__).resolve().parents[2] / 'src/japanmfa/mfa/data/japanese_mfa_v3_phone_map.yaml'

# Full pronunciations from actual G2P or the pinned MFA dictionary.  The owner
# assertion is on the original long phone, not a newly fabricated short phone.
CASES = [
    ('ウェッブ', 'w e bː ɯ', 'bː', ('ッ', 'ブ')),
    ('ネッビオーロ', 'n e bʲː i oː ɾ o', 'bʲː', ('ッ', 'ビ')),
    ('ウッディ', 'ɯ dʲː i', 'dʲː', ('ッ', 'ディ')),
    ('アンミン', 'a mʲː i ɴ', 'mʲː', ('ン', 'ミ')),
    ('アッラー', 'a ɾː aː', 'ɾː', ('ッ', 'ラ')),
    ('カペッリーニ', 'k a p e ɾʲː iː ɲ i', 'ɾʲː', ('ッ', 'リ')),
    ('ンー', 'ɴː', 'ɴː', ('ン', 'ー')),
    ('カッワーリー', 'k a wː aː ɾʲ iː', 'wː', ('ッ', 'ワ')),
    ('イッヒ', 'i çː i', 'çː', ('ッ', 'ヒ')),
    ('ギュッギュ', 'ɟ ɨ ɟː ɨ', 'ɟː', ('ッ', 'ギュ')),
    ('スタッフ', 's ɨ t a ɸː ɯ', 'ɸː', ('ッ', 'フ')),
    ('グリッフィン', 'ɡ ɯ ɾʲ i ɸʲː i ɴ', 'ɸʲː', ('ッ', 'フィ')),
    ('ベッド', 'b e dː o', 'dː', ('ッ', 'ド')),
    ('グッズ', 'ɡ ɯ dzː ɨ', 'dzː', ('ッ', 'ズ')),
    ('ヤッホー', 'j a hː oː', 'hː', ('ッ', 'ホ')),
    ('エッグ', 'e ɡː ɯ', 'ɡː', ('ッ', 'グ')),
    ('ティー', 'tʲ iː', 'tʲ', ('ティ',)),
    ('セッティング', 's e tʲː i ŋ ɡ ɯ', 'tʲː', ('ッ', 'ティ')),
    ('ヴァ', 'v a', 'v', ('ヴァ',)),
    ('ヴィーナス', 'vʲ iː n a s ɨ', 'vʲ', ('ヴィ',)),
    ('フィット', 'ɸʲ i tː o', 'ɸʲ', ('フィ',)),
    ('ブッダ', 'b ɯ dː a', 'dː', ('ッ', 'ダ')),
    ('ヘッダー', 'h e dː aː', 'dː', ('ッ', 'ダ')),
    ('ゴッホ', 'ɡ o hː o', 'hː', ('ッ', 'ホ')),
    ('ヴェロニカ', 'v e ɾ o ɲ i k a', 'v', ('ヴェ',)),
    ('ジャヴォン', 'dʑ a v o ɴ', 'v', ('ヴォ',)),
    ('ラッキー', 'ɾ a cː iː', 'cː', ('ッ', 'キ')),
    ('シュウリョウ', 'ɕ ɨ ɯ ɾʲ oː', 'oː', ('リョ', 'ウ')),
]


@pytest.mark.parametrize('reading,phone_text,target,expected_owners', CASES)
def test_full_pronunciation_retains_original_phone(reading, phone_text, target, expected_owners):
    morae = segment_morae(Token(0, 0, len(reading), reading, (), reading, 'sudachi'))
    phones = tuple(phone_text.split())
    mapping = _match_morae_to_phones(morae, phones, PhoneMap.load(MAP))
    assert len(mapping) == len(phones)
    assert tuple(m.kana for m in mapping[phones.index(target)]) == expected_owners
    assert {m.index_in_token for owners in mapping for m in owners} == set(range(len(morae)))


@pytest.mark.parametrize('reading,phone_text', [
    ('マッタク', 'm a t a k ɯ'),
    ('グッスリ', 'ɡ ɯ dʲː s ɨ ɾʲ i'),
    ('スッゴイ', 's ɨ pː ɡ o i'),
    ('ウェッポ', 'w e bː p o'),
    ('オボロ', 'o bː o ɾ o'),
    ('ギュギュ', 'ɟ ɨ ɟː ɨ'),
    ('プクッリ', 'p ɯ k ɯ e ɾʲː i'),
    ('シャッター', 'ɕ a ɸː ɯ t aː'),
    ('ハーヴィ', 'h aː vʲ iː'),
    ('ソファ', 's o ɸ aː'),
    ('ジョウ', 'dʑ o'),
    ('ウーン', 'ɴː'),
])
def test_wrong_place_missing_or_extra_phone_stays_rejected(reading, phone_text):
    morae = segment_morae(Token(0, 0, len(reading), reading, (), reading, 'sudachi'))
    with pytest.raises(StageFailure):
        _match_morae_to_phones(morae, tuple(phone_text.split()), PhoneMap.load(MAP))
