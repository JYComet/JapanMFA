from __future__ import annotations

import wave
from pathlib import Path

import pytest
from praatio import textgrid

from japanmfa.asr.precomputed_ctc import PrecomputedCTCClient, OriginalAxisWav, read_ctc_words
from japanmfa.domain import Mora, Pronunciation, Token
from japanmfa.frontend.mora import segment_morae
from japanmfa.mfa.g2p import TerminalSokuonG2p
from japanmfa.mfa.phone_map import PhoneMap
from japanmfa.projection import filter_mappable_pronunciations


def _wav(path: Path, frames: int = 16000) -> None:
    with wave.open(str(path), 'wb') as out:
        out.setparams((1, 2, 16000, frames, 'NONE', 'not compressed'))
        out.writeframes(b'\0\0' * frames)


def _grid(path: Path, text: str = '終わっ') -> None:
    grid = textgrid.Textgrid()
    grid.addTier(textgrid.IntervalTier('words', [(0, .2, ''), (.2, .5, text), (.5, 1., '')], 0, 1))
    grid.addTier(textgrid.PointTier('zero_duration', [(.5, 'た')], 0, 1))
    grid.save(str(path), format='long_textgrid', includeBlankSpaces=True)


def test_ctc_point_restores_lexical_stream_and_original_time_axis(tmp_path: Path) -> None:
    source, working, grid = (tmp_path / name for name in ('source.wav', 'working.wav', 'ctc.TextGrid'))
    _wav(source)
    _grid(grid)
    info = OriginalAxisWav().prepare(source, working)
    assert info.source_frames == info.working_frames == 16000
    assert source.read_bytes() == working.read_bytes()
    client = PrecomputedCTCClient({'working': grid}, {'working': '終わった。'})
    result = client.transcribe([working], reference_texts={working: '終わった。'})[working]
    assert [(item.text, item.start, item.end) for item in result.lexical_timestamps] == [
        ('終わっ', .2, .5), ('た', .5, .5)]


def test_ctc_mismatch_is_rejected_before_mfa(tmp_path: Path) -> None:
    grid = tmp_path / 'ctc.TextGrid'
    _grid(grid, '違う')
    with pytest.raises(ValueError, match='lexical'):
        read_ctc_words(grid, '終わった。', 1.)


def test_ctc_out_of_audio_is_rejected(tmp_path: Path) -> None:
    grid = tmp_path / 'ctc.TextGrid'
    _grid(grid)
    with pytest.raises(ValueError, match='duration'):
        read_ctc_words(grid, '終わった。', .7)


def test_terminal_sokuon_adds_glottal_stop_only_when_model_omits_it(tmp_path: Path) -> None:
    class StubG2p:
        def pronounce(self, readings, work_dir):
            return (Pronunciation('ダッ', ('d', 'a')),
                    Pronunciation('ナカッ', ('n', 'a', 'k', 'a', 'ʔ')),
                    Pronunciation('タ', ('t', 'a')))

    result = TerminalSokuonG2p(StubG2p()).pronounce(('ダッ', 'ナカッ', 'タ'), tmp_path)
    assert result[0].phones == ('d', 'a', 'ʔ')
    assert result[1].phones == ('n', 'a', 'k', 'a', 'ʔ')
    assert result[2].phones == ('t', 'a')


@pytest.mark.parametrize(('reading', 'phones'), [
    ('スーパー', ('s', 'ɨː', 'p', 'aː')),
    ('カンケイ', ('k', 'a', 'ŋ', 'k', 'eː')),
    ('ソレ', ('s', 'o', 'ɾ', 'e')),
    ('ダッ', ('d', 'a', 'ʔ')),
    ('キッチン', ('c', 'i', 'tɕː', 'i', 'ɴ')),
    ('ゼッタイ', ('z', 'e', 'tː', 'a', 'i')),
    ('シュッキン', ('ɕ', 'ɨ', 'cː', 'i', 'ɴ')),
    ('オオアワテ', ('oː', 'a', 'w', 'a', 't', 'e')),
    ('シーズン', ('ɕ', 'iː', 'z', 'ɨ', 'ɴ')),
    ('キョウ', ('c', 'oː')),
    ('エー', ('eː',)),
    ('ブー', ('b', 'ɯː')),
    ('ブーブー', ('b', 'ɯː', 'b', 'ɯː')),
    ('ウェイトレス', ('ɯ', 'e', 'i', 't', 'o', 'ɾ', 'e', 's', 'ɨ')),
    ('ウェイトレス', ('w', 'e', 'i', 't', 'o', 'ɾ', 'e', 's', 'ɨ')),
    ('ジャア', ('dʑ', 'a', 'a')),
    ('ガッキ', ('ɡ', 'a', 'cː', 'i')),
    ('カワイイ', ('k', 'a', 'w', 'a', 'iː')),
])
def test_observed_game_g2p_has_mora_owners(reading: str, phones: tuple[str, ...]) -> None:
    token = Token(0, 0, len(reading), reading, ('名詞',), reading, 'sudachi')
    morae = tuple(Mora(0, i, item.kana, None) for i, item in enumerate(segment_morae(token)))
    phone_map = PhoneMap.load(Path('src/japanmfa/mfa/data/japanese_mfa_v3_phone_map.yaml'))
    result = filter_mappable_pronunciations(
        (token,), (Pronunciation(reading, phones),), {0: morae}, phone_map)
    assert result[0].phones == phones


@pytest.mark.parametrize(('points', 'reference'), [
    (('ん', 'だ', 'けど'), '聞いたんだけどね。'),
    (('あ', 'あ', 'ん'), '聞いたああんね。'),
])
def test_ctc_simultaneous_points_keep_serialized_lexical_order(
        tmp_path: Path, points: tuple[str, ...], reference: str) -> None:
    from tools.galgame_qwen_ctc import render_textgrid

    grid = tmp_path / 'ctc.TextGrid'
    words = [{'text': '聞いた', 'start': .2, 'end': .5}]
    words.extend({'text': label, 'start': .5, 'end': .5} for label in points)
    words.append({'text': 'ね', 'start': .5, 'end': .8})
    grid.write_text(render_textgrid(1., words), encoding='utf-8')
    result = read_ctc_words(grid, reference, 1.)
    assert [item.text for item in result] == ['聞いた', *points, 'ね']
    assert [(item.start, item.end) for item in result] == [
        (.2, .5), (.5, .5), (.5, .5), (.5, .5), (.5, .8)]
    with pytest.raises(ValueError, match='lexical'):
        read_ctc_words(grid, '聞いた別の言葉ね。', 1.)


def test_observed_suggoku_wrong_place_stop_is_still_rejected() -> None:
    from japanmfa.errors import StageFailure

    reading = 'スッゴク'
    token = Token(0, 0, len(reading), reading, ('副詞',), reading, 'sudachi')
    morae = segment_morae(token)
    phone_map = PhoneMap.load(Path('src/japanmfa/mfa/data/japanese_mfa_v3_phone_map.yaml'))
    pronunciation = Pronunciation(reading, ('s', 'ɨ', 'pː', 'ɡ', 'o', 'k', 'ɯ'))
    with pytest.raises(StageFailure) as failure:
        filter_mappable_pronunciations((token,), (pronunciation,), {0: morae}, phone_map)
    assert failure.value.reason_code == 'no_mappable_pronunciation'
