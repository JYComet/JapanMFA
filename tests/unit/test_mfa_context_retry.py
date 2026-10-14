from dataclasses import replace
from types import SimpleNamespace
import wave
import pytest
from japanmfa.asr.qwen3 import Timestamp
from japanmfa.domain import Token
from japanmfa.mfa.timed import plan_timed_segments
from japanmfa.pipeline import MfaPrepared, PreparationState
from japanmfa.mfa.context_retry import prepare_context_retry


def prepared(tmp_path, gap=0.0):
    audio=tmp_path/'audio.wav'
    with wave.open(str(audio),'wb') as f:
        f.setparams((1,2,16000,0,'NONE','not compressed'));f.writeframes(b'\0\0'*48000)
    text='世界大丈夫'
    tokens=(Token(0,0,2,'世界',('名詞',),'セカイ','sudachi'),Token(1,2,5,'大丈夫',('名詞',),'ダイジョウブ','sudachi'))
    times=(Timestamp('世界',.2,.9),Timestamp('大丈夫',.9+gap,1.8+gap))
    segments=plan_timed_segments(text,times,tokens,3.)
    values={'source':SimpleNamespace(original=text),'tokens':tokens,'asr_result':SimpleNamespace(lexical_timestamps=times),
            'audio_info':SimpleNamespace(duration=3.),'segments':segments}
    state=PreparationState('prepared',None,values,{},'identity')
    return MfaPrepared('source',tmp_path,audio,tmp_path/'dict',audio,('one','two'),segments,state)


def test_recovery_merges_context_but_retains_original_review_anchors(tmp_path):
    original=prepared(tmp_path)
    retry=prepare_context_retry(original)
    assert len(retry.segments)==1
    assert (retry.segments[0].first_token,retry.segments[0].last_token)==(0,2)
    assert retry.state.values['review_segments']==original.segments
    assert retry.state.values['segments']==retry.segments
    assert original.state.values['segments']==original.segments
    assert 'review_segments' not in original.state.values
    assert retry.aliases==original.aliases and retry.dictionary==original.dictionary
    assert retry.state.identity==original.state.identity


def test_long_ctc_silence_remains_a_cut(tmp_path):
    assert prepare_context_retry(prepared(tmp_path,gap=.5)) is None


def test_single_segment_and_unverified_preparation_do_not_retry(tmp_path):
    original=prepared(tmp_path)
    assert prepare_context_retry(replace(original,state=None)) is None
    retry=prepare_context_retry(original)
    assert prepare_context_retry(retry) is None


def test_missing_or_changed_source_is_not_silently_accepted(tmp_path):
    original=prepared(tmp_path);original.working_audio.unlink()
    with pytest.raises(FileNotFoundError):prepare_context_retry(original)


def clipped_tail(tmp_path, kind="decay"):
    import numpy as np
    original=prepared(tmp_path,gap=.5)
    end=original.segments[0].end
    t=np.arange(48000)/16000
    amplitude=np.where((t>=.2)&(t<end),.24,0.)
    if kind=="flat": tail=np.where((t>=end)&(t<end+.2),.24,0.)
    elif kind=="detached": tail=np.where((t>=end+.05)&(t<end+.2),.24,0.)
    elif kind=="long": tail=np.where((t>=end)&(t<end+.5),.24*np.exp(-12*np.maximum(0,t-end)),0.)
    else:
        tail=np.where((t>=end)&(t<end+.2),.24*np.exp(-30*np.maximum(0,t-end)),0.)
        if kind=="reattack":tail=np.where((t>=end+.07)&(t<end+.14),.24,tail)
    amplitude+=tail
    signal=(amplitude*np.sin(2*np.pi*200*t)*32767).astype('<i2')
    with wave.open(str(original.working_audio),'wb') as f:
        f.setparams((1,2,16000,0,'NONE','not compressed'));f.writeframes(signal.tobytes())
    diag={"passed":False,"reason_code":"alignment_acoustic_coverage", "raw_phones":[
        {"start":end-.05,"end":end,"label":"t" if kind=="consonant" else "o", "silence":False,"token_index":original.segments[0].last_token-1}]}
    return original,diag


def test_clipped_vowel_decay_requests_native_context_without_moving_phone(tmp_path):
    original,diag=clipped_tail(tmp_path)
    retry=prepare_context_retry(original,failed_postprocess=diag)
    assert retry is not None and len(retry.segments)==len(original.segments)
    assert original.segments[0].end+.12 < retry.segments[0].end <= original.segments[0].end+.23
    assert retry.segments[0].end<=original.segments[1].start
    assert retry.segments[0].anchor_end==original.segments[0].anchor_end
    assert retry.segments[0].acoustic_end_limit>original.segments[0].end
    assert [s.anchor_end for s in retry.state.values['review_segments']]==[s.anchor_end for s in original.segments]
    assert diag['raw_phones'][0]['end']==original.segments[0].end
    assert retry.aliases==original.aliases and retry.dictionary==original.dictionary
    assert prepare_context_retry(retry,failed_postprocess=diag) is None


@pytest.mark.parametrize('kind',['flat','reattack','detached','long','consonant'])
def test_clipped_tail_context_rejects_unverified_extension(tmp_path,kind):
    original,diag=clipped_tail(tmp_path,kind)
    assert prepare_context_retry(original,failed_postprocess=diag) is None


def test_clipped_context_never_retries_passed_or_non_edge_phone(tmp_path):
    original,diag=clipped_tail(tmp_path)
    diag['passed']=True
    assert prepare_context_retry(original,failed_postprocess=diag) is None
    diag['passed']=False;diag['raw_phones'][0]['end']-=.02
    assert prepare_context_retry(original,failed_postprocess=diag) is None



def test_clipped_retry_reuses_only_exact_original_crops(tmp_path):
    from japanmfa.mfa.context_retry import clipped_retry_inputs
    from japanmfa.mfa.hybrid_batch import BatchCorpus, BatchEntry
    from tools.galgame_mfa_from_ctc import sha
    import json
    corpus=tmp_path/'corpus';corpus.mkdir()
    for name in ['changed','kept']:
        (corpus/(name+'.wav')).write_bytes(b'unchanged wave bytes')
        (corpus/(name+'.lab')).write_text('jmfa_000001\n')
    old=tmp_path/'old.TextGrid';old.write_text('            text = "jmfa_000009"\n            text = "a"\n            text = "\\u0291"\n')
    dictionary=tmp_path/'dictionary';dictionary.write_text('jmfa_000001 a\n')
    entries={name:BatchEntry(name,'source',i,('local',),('jmfa_000001',),sha(corpus/(name+'.wav'))) for i,name in enumerate(['changed','kept'])}
    batch=BatchCorpus('timed',tmp_path,corpus,dictionary,entries)
    previous=replace(entries['kept'],name='original',global_aliases=('jmfa_000009',))
    initial={('source',1):(previous,old)}
    subset,reused=clipped_retry_inputs(batch,initial,{'source':{0}})
    assert set(subset.entries)=={'changed'} and set(reused)=={'kept'}
    assert set(p.name for p in subset.corpus_dir.iterdir())=={'changed.wav','changed.lab'}
    assert sha(subset.corpus_dir/'changed.wav')==entries['changed'].wav_sha256
    assert 'jmfa_000001' in reused['kept'].read_text() and 'jmfa_000009' not in reused['kept'].read_text()
    assert old.read_text().startswith('            text = "jmfa_000009"')
    assert reused['kept'].read_text().splitlines()[2]==old.read_text().splitlines()[2]
    assert json.loads((tmp_path/'clipped-retry-selection.json').read_text())['reused'][0]['original_textgrid_sha256']==sha(old)


def test_clipped_retry_refuses_changed_audio_identity(tmp_path):
    from japanmfa.mfa.context_retry import clipped_retry_inputs
    from japanmfa.mfa.hybrid_batch import BatchCorpus, BatchEntry
    corpus=tmp_path/'corpus';corpus.mkdir()
    entry=BatchEntry('kept','source',1,('local',),('global',),'current-sha')
    previous=replace(entry,wav_sha256='wrong-sha')
    with pytest.raises(ValueError,match='identity'):
        clipped_retry_inputs(BatchCorpus('timed',tmp_path,corpus,tmp_path/'dict',{'kept':entry}),
                             {('source',1):(previous,tmp_path/'old')},{'source':{0}})



@pytest.mark.parametrize('offset',[.206,.207,.209,.215])
def test_clipped_retry_respects_subframe_next_crop_start(tmp_path,offset):
    original,diag=clipped_tail(tmp_path)
    second=replace(original.segments[1],start=original.segments[0].end+offset)
    original=replace(original,segments=(original.segments[0],second))
    retry=prepare_context_retry(original,failed_postprocess=diag)
    assert retry is None or retry.segments[0].end<=second.start


def test_connected_decay_support_keeps_ctc_anchors_and_original_evidence(tmp_path):
    import numpy as np
    original=prepared(tmp_path,gap=.5)
    first=replace(original.segments[0],end=1.36,anchor_end=1.12,acoustic_end_limit=1.24)
    second=replace(original.segments[1],start=1.60)
    original=replace(original,segments=(first,second))
    t=np.arange(48000)/16000
    amplitude=np.where((t>=1.08)&(t<1.44),.30*np.exp(-18*np.maximum(0,t-1.12)),0.)
    signal=(amplitude*np.sin(2*np.pi*200*t)*32767).astype('<i2')
    with wave.open(str(original.working_audio),'wb') as f:
        f.setparams((1,2,16000,0,'NONE','not compressed'));f.writeframes(signal.tobytes())
    diag={"passed":False,"reason_code":"alignment_acoustic_coverage","raw_phones":[
        {"start":1.30,"end":1.36,"label":"o","silence":False,"token_index":original.segments[0].last_token-1}]}
    retry=prepare_context_retry(original,failed_postprocess=diag)
    assert retry is not None
    review=retry.state.values['review_segments'][0]
    assert (review.start,review.end,review.anchor_start,review.anchor_end,review.first_token,review.last_token)==(first.start,first.end,first.anchor_start,first.anchor_end,first.first_token,first.last_token)
    assert 1.40<=review.acoustic_end_limit<=1.44
    assert retry.segments[0].end<=second.start
    assert retry.state.values['original_review_segments']==original.segments
    assert original.segments[0].acoustic_end_limit==1.24


def test_decay_support_does_not_override_more_than_350ms_anchor_drift(tmp_path):
    original,diag=clipped_tail(tmp_path)
    first=replace(original.segments[0],anchor_end=original.segments[0].end-.3,acoustic_end_limit=original.segments[0].end-.1)
    original=replace(original,segments=(first,original.segments[1]))
    retry=prepare_context_retry(original,failed_postprocess=diag)
    assert retry is not None
    assert retry.state.values['review_segments']==original.segments


@pytest.mark.parametrize('field',['bgm_suspects','low_energy_phone_issues','unowned_speech_regions'])
def test_clipped_retry_preserves_other_original_vetoes(tmp_path,field):
    original,diag=clipped_tail(tmp_path)
    diag[field]=[{'reason':'other veto'}]
    assert prepare_context_retry(original,failed_postprocess=diag) is None


def test_clipped_retry_requires_last_token_owner(tmp_path):
    original,diag=clipped_tail(tmp_path)
    diag['raw_phones'][0]['token_index']=original.segments[0].last_token
    assert prepare_context_retry(original,failed_postprocess=diag) is None


def test_clipped_retry_does_not_mix_with_context_merging(tmp_path,monkeypatch):
    original,diag=clipped_tail(tmp_path)
    def forbidden(*args,**kwargs):raise AssertionError('clipped and merge retries must be separate')
    monkeypatch.setattr('japanmfa.mfa.context_retry.plan_timed_segments',forbidden)
    retry=prepare_context_retry(original,failed_postprocess=diag)
    assert retry is not None and len(retry.segments)==len(original.segments)


def test_clipped_retry_preserves_original_structural_veto(tmp_path):
    original,diag=clipped_tail(tmp_path)
    diag['structural_issues']=[{'reason':'overlap_or_out_of_axis'}]
    assert prepare_context_retry(original,failed_postprocess=diag) is None
