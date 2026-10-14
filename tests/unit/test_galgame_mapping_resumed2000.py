from pathlib import Path
import pytest
from japanmfa.domain import Mora
from japanmfa.errors import StageFailure
from japanmfa.mfa.phone_map import PhoneMap
from japanmfa.projection import _match_morae_to_phones, labels_for_phone
MAP_PATH=Path.cwd()/'src/japanmfa/mfa/data/japanese_mfa_v3_phone_map.yaml'
CASES=[(['シャ', 'ー'], ['ɕ', 'aː']), (['ベ', 'ー'], ['b', 'eː']), (['ジュ', 'ウ'], ['ʑ', 'ɨː']), (['チ', 'イ'], ['tɕ', 'iː']), (['ッ', 'プ'], ['pː', 'ɯ']), (['ッ', 'ポ'], ['pː', 'o']), (['ッ', 'ジ'], ['dʑː', 'i']), (['ル', 'ー'], ['ɾ', 'ɯː']), (['ケ', 'ー'], ['k', 'eː']), (['チ', 'ー'], ['tɕ', 'iː']), (['ニ', 'イ'], ['ɲ', 'iː']), (['ショ', 'ー'], ['ɕ', 'oː']), (['ヒュ', 'ー'], ['ç', 'ɨː']), (['ッ', 'チャ'], ['tɕː', 'a']), (['ッ', 'サ'], ['sː', 'a']), (['ッ', 'セ'], ['sː', 'e']), (['ヅ'], ['z', 'ɨ']), (['ゴ', 'ー'], ['ɡ', 'oː']), (['マ', 'ー'], ['m', 'aː']), (['ト', 'ー'], ['t', 'oː'])]
NEGATIVE=[(['ケ', 'ッ', 'コ', 'ウ'], ['k', 'e', 'k', 'oː']), (['オ', 'ッ', 'パ', 'イ'], ['o', 'p', 'a', 'i']), (['ト', 'ッ'], ['t', 'o', 'pː']), (['チ', 'ッ', 'チャ', 'イ'], ['tɕ', 'i', 'tɕ', 'a', 'i']), (['ッ', 'ポ', 'イ'], ['tː', 'p', 'o', 'i']), (['イ', 'タ', 'ズ', 'ラ'], ['i', 't', 'a', 'c', 'i', 'z', 'ɨ', 'ɾ', 'a'])]
@pytest.mark.parametrize('kana,phones', CASES)
def test_exact_observed_resumed2000_mora_owners(kana,phones):
    morae=tuple(Mora(0,i,k,'H' if i==0 else 'L') for i,k in enumerate(kana))
    owners=_match_morae_to_phones(morae,tuple(phones),PhoneMap.load(MAP_PATH))
    assert len(owners)==len(phones)
    assert {m.index_in_token for group in owners for m in group}==set(range(len(kana)))
    for group in owners: labels_for_phone(group)
@pytest.mark.parametrize('kana,phones', NEGATIVE)
def test_missing_inserted_or_wrong_geminate_stays_rejected(kana,phones):
    morae=tuple(Mora(0,i,k,'H') for i,k in enumerate(kana))
    with pytest.raises(StageFailure):
        _match_morae_to_phones(morae,tuple(phones),PhoneMap.load(MAP_PATH))
