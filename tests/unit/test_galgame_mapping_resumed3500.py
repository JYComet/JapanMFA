from pathlib import Path
import pytest
from japanmfa.domain import Mora
from japanmfa.errors import StageFailure
from japanmfa.mfa.phone_map import PhoneMap
from japanmfa.projection import _match_morae_to_phones, labels_for_phone
MAP_PATH=Path.cwd()/'src/japanmfa/mfa/data/japanese_mfa_v3_phone_map.yaml'
CASES=[(['ポ'], ['p', 'o']), (['ミャ'], ['mʲ', 'a']), (['ピ'], ['pʲ', 'i']), (['ヒ', 'ー'], ['ç', 'iː']), (['ヤ', 'ー'], ['j', 'aː']), (['ラ', 'ー'], ['ɾ', 'aː']), (['チェ', 'ー'], ['tɕ', 'eː']), (['ガ', 'ー'], ['ɡ', 'aː']), (['ッ', 'ツァ'], ['tsː', 'a']), (['ウ', 'ー'], ['ɯː'])]
NEGATIVE=[(['ガ', 'ッ', 'コ', 'ウ'], ['ɡ', 'a', 'k', 'oː']), (['チ', 'ッ', 'チャ', 'イ'], ['tɕ', 'i', 'tɕ', 'a', 'i']), (['キ', 'ン', 'エ', 'ン'], ['c', 'i', 'e', 'ɴ']), (['サ', 'ビ', 'シ', 'イ'], ['s', 'a', 'bʲ', 'i', 'ɕ', 'i']), (['ウ', 'ー', 'ン'], ['ɯ', 'ɴ']), (['ー'], ['iː'])]
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
