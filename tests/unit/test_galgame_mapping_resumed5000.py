from pathlib import Path
import pytest
from japanmfa.domain import Mora
from japanmfa.errors import StageFailure
from japanmfa.mfa.phone_map import PhoneMap
from japanmfa.projection import _match_morae_to_phones, labels_for_phone
MAP_PATH=Path.cwd()/'src/japanmfa/mfa/data/japanese_mfa_v3_phone_map.yaml'
CASES=[(['ヒャ'], ['ç', 'a']), (['ミョ'], ['mʲ', 'o']), (['キャ', 'ー'], ['c', 'aː']), (['グ', 'ー'], ['ɡ', 'ɯː']), (['ク', 'ー'], ['k', 'ɯː']), (['シ', 'イ'], ['ɕ', 'iː'])]
NEGATIVE=[(['ラ', 'シ', 'イ'], ['ɾ', 'a', 'ɕ', 'i']), (['ヒ', 'ッ', 'コ', 'シ'], ['ç', 'i', 'k', 'o', 'ɕ', 'i']), (['ス', 'ッ', 'ゴ', 'イ'], ['s', 'ɨ', 'pː', 'ɡ', 'o', 'i']), (['ク', 'ッ', 'シ'], ['k', 'ɯ', 'ɕː']), (['ビョ', 'ウ', 'キ'], ['bʲ', 'i', 'oː', 'c', 'i']), (['ー'], ['ɯː'])]
@pytest.mark.parametrize('kana,phones', CASES)
def test_observed_precise_mora_owners(kana,phones):
    morae=tuple(Mora(0,i,k,'H' if i==0 else 'L') for i,k in enumerate(kana))
    owners=_match_morae_to_phones(morae,tuple(phones),PhoneMap.load(MAP_PATH))
    assert len(owners)==len(phones)
    assert {m.index_in_token for group in owners for m in group}==set(range(len(kana)))
    for group in owners: labels_for_phone(group)
@pytest.mark.parametrize('kana,phones', NEGATIVE)
def test_missing_or_ambiguous_mora_stays_rejected(kana,phones):
    morae=tuple(Mora(0,i,k,'H') for i,k in enumerate(kana))
    with pytest.raises(StageFailure): _match_morae_to_phones(morae,tuple(phones),PhoneMap.load(MAP_PATH))
