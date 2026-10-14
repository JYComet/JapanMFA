from pathlib import Path
import pytest
from japanmfa.domain import Mora
from japanmfa.errors import StageFailure
from japanmfa.mfa.phone_map import PhoneMap
from japanmfa.projection import _match_morae_to_phones, labels_for_phone
MAP_PATH=Path.cwd()/'src/japanmfa/mfa/data/japanese_mfa_v3_phone_map.yaml'
CASES=[(['ジェ'], ['dʑ', 'e']), (['ジュ'], ['ʑ', 'ɨ']), (['ワ', 'ー'], ['w', 'aː']), (['ノ', 'ウ'], ['n', 'oː']), (['ゲ', 'ー'], ['ɡ', 'eː']), (['ペ', 'ー'], ['p', 'eː']), (['ネ', 'ー'], ['n', 'eː']), (['ジャ', 'ー'], ['ʑ', 'aː']), (['ッ', 'ケ', 'ー'], ['kː', 'eː']), (['ッ', 'ピ'], ['pʲː', 'i'])]
NEGATIVE=[(['オ', 'ー', 'ナ', 'ー'], ['oː', 'aː', 'n', 'aː']), (['ソ', 'ファ'], ['s', 'o', 'ɸ', 'aː']), (['ケ', 'ッ', 'コ', 'ウ'], ['k', 'e', 'k', 'oː']), (['カ', 'ッ', 'テ', 'ニ'], ['k', 'a', 't', 'e', 'ɲ', 'i']), (['セ', 'ッ', 'チャ', 'ク'], ['s', 'e', 'tɕ', 'a', 'k', 'ɯ']), (['ー'], ['iː'])]
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
