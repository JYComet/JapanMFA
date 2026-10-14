from pathlib import Path
import pytest
from japanmfa.domain import Mora
from japanmfa.errors import StageFailure
from japanmfa.mfa.phone_map import PhoneMap
from japanmfa.projection import _match_morae_to_phones, labels_for_phone

MAP_PATH = Path.cwd() / 'src/japanmfa/mfa/data/japanese_mfa_v3_phone_map.yaml'
CASES = [(['ア', 'ー'], ['aː']), (['ヘ', 'ー'], ['h', 'eː']), (['サ', 'ー'], ['s', 'aː']), (['ハ', 'ー'], ['h', 'aː']), (['ギャ'], ['ɟ', 'a']), (['リャ'], ['ɾʲ', 'a']), (['リョ'], ['ɾʲ', 'o']), (['ズ'], ['dz', 'ɨ']), (['ヅ'], ['dz', 'ɨ']), (['コ', 'ウ'], ['k', 'oː']), (['ゾ', 'ウ'], ['dz', 'oː']), (['ッ', 'ク'], ['kː', 'ɯ'])]

@pytest.mark.parametrize('kana,phones', CASES)
def test_observed_resumed1000_candidates_cover_exact_morae(kana, phones):
    morae = tuple(Mora(0, i, value, 'H' if i == 0 else 'L') for i, value in enumerate(kana))
    mapped = _match_morae_to_phones(morae, tuple(phones), PhoneMap.load(MAP_PATH))
    assert {m.index_in_token for group in mapped for m in group} == set(range(len(kana)))
    assert len(mapped) == len(phones)
    for group in mapped:
        labels_for_phone(group)

@pytest.mark.parametrize('kana,phones', [
    (('ガ', 'ッ', 'コ', 'ウ'), ('ɡ', 'a', 'k', 'oː')),
    (('ケ', 'ッ', 'コ', 'ウ'), ('k', 'e', 'k', 'oː')),
    (('ト', 'ッ'), ('t', 'o', 'pː')),
])
def test_missing_or_wrong_sokuon_is_still_rejected(kana, phones):
    morae = tuple(Mora(0, i, value, 'H') for i, value in enumerate(kana))
    with pytest.raises(StageFailure):
        _match_morae_to_phones(morae, phones, PhoneMap.load(MAP_PATH))
