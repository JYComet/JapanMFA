"""All 83 pinned acoustic-model phones have full dictionary-word witnesses."""
import json
from pathlib import Path
import pytest
from japanmfa.domain import Token
from japanmfa.errors import StageFailure
from japanmfa.frontend.mora import segment_morae
from japanmfa.mfa.phone_map import PhoneMap
from japanmfa.projection import _match_morae_to_phones

ROOT=Path(__file__).resolve().parents[2]
EVIDENCE=json.loads((ROOT/'tests/fixtures/japanese_mfa_v3_phone_inventory.json').read_text())
MAP=ROOT/'src/japanmfa/mfa/data/japanese_mfa_v3_phone_map.yaml'


def assert_full_word(reading,phones,phone_map):
    morae=segment_morae(Token(0,0,len(reading),reading,(),reading,'sudachi'))
    owners=_match_morae_to_phones(morae,tuple(phones),phone_map)
    assert len(owners)==len(phones)
    assert all(owners)
    assert {m.index_in_token for group in owners for m in group}==set(range(len(morae)))


def test_every_model_phone_has_a_witness_and_a_rule():
    phone_map=PhoneMap.load(MAP)
    inventory=set(EVIDENCE['model_phones'])
    assert len(inventory)==83
    assert {c['phone'] for c in EVIDENCE['cases']}==inventory
    assert not {p for p in inventory if phone_map.normalize(p) not in phone_map.known_phones}
    assert set(EVIDENCE['non_speech_symbols'])=={'<eps>','sil','spn'}
    assert not inventory.intersection(EVIDENCE['non_speech_symbols'])


@pytest.mark.parametrize('case',EVIDENCE['cases'],ids=lambda c:c['phone'])
def test_model_phone_full_dictionary_word_without_splitting(case):
    assert case['phone'] in case['phones']
    assert_full_word(case['reading'],case['phones'],PhoneMap.load(MAP))


@pytest.mark.parametrize('case',EVIDENCE['new_rule_word_cases'])
def test_devoiced_rule_has_a_complete_dictionary_word(case):
    phone_map=PhoneMap.load(MAP)
    proof=case['full_word_proof']
    assert_full_word(proof['reading'],proof['phones'],phone_map)
    rule=phone_map.rule_for(tuple(case['kana']),tuple(case['phones']))
    assert rule.mora_spans==tuple(tuple(x) for x in case['mora_spans'])
    for phone in case['phones']:
        if '̥' in phone:assert phone_map.normalize(phone)==phone


@pytest.mark.parametrize('reading,phones',[
    ('カ',('k','i̥')),('シー',('ɕ','i̥')),('ッキ',('c','i̥')),('ス',('s','i̥')),
])
def test_devoicing_does_not_accept_wrong_vowels_or_missing_length(reading,phones):
    with pytest.raises(StageFailure):assert_full_word(reading,phones,PhoneMap.load(MAP))
