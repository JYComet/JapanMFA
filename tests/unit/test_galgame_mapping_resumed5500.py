from pathlib import Path
import pytest
from japanmfa.domain import Mora
from japanmfa.errors import StageFailure
from japanmfa.mfa.phone_map import PhoneMap
from japanmfa.projection import _match_morae_to_phones, labels_for_phone
MAP_PATH=Path.cwd()/'src/japanmfa/mfa/data/japanese_mfa_v3_phone_map.yaml'
CASES=[(['ギョ'], ['ɟ','o'], [[0],[0]]), (['プ','ー'], ['p','ɯː'], [[0],[0,1]])]
NEGATIVE=[(['ギョ'], ['ɟ','i','o']), (['プ','ー'], ['p','ɯ']), (['エ','イ','ギョ','ウ'], ['e','i','ɟ','o']), (['セ','ッ','カ','ク'], ['s','e','k','a','k','ɯ']), (['ス','ッ','ゴ','イ'], ['s','ɨ','pː','ɡ','o','i']), (['チュ','ウ','チョ'], ['tɕ','ɨː','tɕː','o'])]
@pytest.mark.parametrize('kana,phones,expected', CASES)
def test_observed_precise_mora_owners(kana,phones,expected):
    morae=tuple(Mora(0,i,k,'H' if i==0 else 'L') for i,k in enumerate(kana))
    owners=_match_morae_to_phones(morae,tuple(phones),PhoneMap.load(MAP_PATH))
    assert [[m.index_in_token for m in group] for group in owners]==expected
    for group in owners: labels_for_phone(group)
@pytest.mark.parametrize('kana,phones', NEGATIVE)
def test_missing_extra_or_mismatched_mora_stays_rejected(kana,phones):
    morae=tuple(Mora(0,i,k,'H') for i,k in enumerate(kana))
    with pytest.raises(StageFailure): _match_morae_to_phones(morae,tuple(phones),PhoneMap.load(MAP_PATH))
