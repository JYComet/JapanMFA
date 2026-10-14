from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

from japanmfa.asr.qwen3 import Timestamp
from japanmfa.domain import Token
from japanmfa.mfa.textgrid import MfaAlignment, MfaPhone, MfaWord
from japanmfa.mfa.word_fusion import fuse_word_boundaries
from japanmfa.output.reports import write_json


def _wav(path: Path, active: tuple[tuple[float, float], ...]) -> None:
    samples = np.zeros(16000, dtype=np.int16)
    for start, end in active:
        first, last = round(start * 16000), round(end * 16000)
        samples[first:last] = (np.sin(np.arange(last - first) * .21) * 9000).astype(np.int16)
    with wave.open(str(path), "wb") as output:
        output.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        output.writeframes(samples.tobytes())


def _one_word(start: float, end: float, *, silence: bool = False) -> MfaAlignment:
    middle = (start + end) / 2
    phones = [MfaPhone("a", start, middle, "w0", False),
              MfaPhone("b", middle, end, "w0", False)]
    if silence:
        phones.append(MfaPhone("sp", end, 1.0, None, True))
    return MfaAlignment((MfaWord("w0", start, end),), tuple(phones), ())


def _token(text: str) -> Token:
    return Token(0, 0, len(text), text, (), text, "override")


def test_quiet_ctc_tail_trims_word_and_scales_phones(tmp_path: Path) -> None:
    audio = tmp_path / "quiet-tail.wav"
    _wav(audio, ((.2, .55),))
    raw = _one_word(.2, .7)

    fused, report = fuse_word_boundaries(
        raw, "あ", (_token("あ"),), (Timestamp("あ", .2, .5, "ctc"),), audio,
    )

    assert fused.words[0].end == .6
    assert fused.phones[-1].end == .6
    assert fused.phones[0].end == .4
    assert report["edits"][0]["edge"] == "end"


def test_voiced_ctc_tail_is_not_trimmed(tmp_path: Path) -> None:
    audio = tmp_path / "voiced-tail.wav"
    _wav(audio, ((.2, .7),))
    raw = _one_word(.2, .7)

    fused, report = fuse_word_boundaries(
        raw, "あ", (_token("あ"),), (Timestamp("あ", .2, .5, "ctc"),), audio,
    )

    assert fused == raw
    assert report["edits"] == []


def test_connected_voice_extends_word_and_moves_explicit_silence(tmp_path: Path) -> None:
    audio = tmp_path / "connected.wav"
    _wav(audio, ((.2, .72),))
    raw = _one_word(.2, .6, silence=True)

    fused, report = fuse_word_boundaries(
        raw, "あ", (_token("あ"),), (Timestamp("あ", .2, .8, "ctc"),), audio,
    )

    assert fused.words[0].end == .7
    assert fused.phones[1].end == .7
    assert fused.phones[2].start == .7
    assert report["edits"][0]["edge"] == "end"


def test_zero_duration_and_large_drift_never_rescale_phones(tmp_path: Path) -> None:
    audio = tmp_path / "unchanged.wav"
    _wav(audio, ((.2, .6),))
    raw = _one_word(.2, .6)

    zero, _ = fuse_word_boundaries(
        raw, "あ", (_token("あ"),), (Timestamp("あ", .5, .5, "ctc"),), audio,
    )
    large, _ = fuse_word_boundaries(
        raw, "あ", (_token("あ"),), (Timestamp("あ", .55, .95, "ctc"),), audio,
    )
    assert zero == raw
    assert large == raw


def test_different_ctc_segmentation_does_not_pair_by_array_index(tmp_path: Path) -> None:
    audio = tmp_path / "segmentation.wav"
    _wav(audio, ((.2, .7),))
    tokens = (Token(0, 0, 2, "あい", (), "アイ", "override"),)
    raw = _one_word(.2, .7)

    fused, report = fuse_word_boundaries(
        raw, "あい", tokens,
        (Timestamp("あ", .2, .4, "ctc"), Timestamp("い", .4, .7, "ctc")), audio,
    )

    assert fused == raw
    assert report["matched_words"] == 0


def test_fusion_conflict_keeps_linguistic_index_in_written_report(tmp_path: Path) -> None:
    audio = tmp_path / "zero.wav"
    _wav(audio, ((.2, .6),))
    _, report = fuse_word_boundaries(
        _one_word(.2, .6), "あ", (_token("あ"),),
        (Timestamp("あ", .5, .5, "ctc"),), audio,
    )
    path = tmp_path / "postprocess.json"
    write_json(path, {"ctc_word_fusion": report})

    import json
    saved = json.loads(path.read_text())
    assert saved["ctc_word_fusion"]["conflicts"][0]["token_index"] == 0
