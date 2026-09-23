import array
import math
import wave
from pathlib import Path

import pytest

from japanmfa.domain import Mora, PhoneAnnotation, PhoneInterval
from japanmfa.postprocess import postprocess_annotations


def write_wave(path: Path, regions: tuple[tuple[float, float], ...], duration: float = 1.0) -> None:
    samples = array.array("h", (int(8000 * math.sin(2 * math.pi * 200 * i / 16000)) if any(a <= i / 16000 < b for a, b in regions) else 0 for i in range(round(duration * 16000))))
    with wave.open(str(path), "wb") as out:
        out.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        out.writeframes(samples.tobytes())


def phone(start: float, end: float) -> PhoneAnnotation:
    return PhoneAnnotation(PhoneInterval(start, end, "a"), 0, (Mora(0, 0, "ア", "H"),), "ア", "HH", False)


def test_postprocess_detects_audio_misclassified_as_silence(tmp_path: Path) -> None:
    audio = tmp_path / "a.wav"
    write_wave(audio, ((.05, .4), (.7, .85)))
    result = postprocess_annotations(audio, 1., (phone(.68, .9),))
    assert not result.report["passed"]
    assert result.report["reason_code"] == "alignment_acoustic_coverage"
    assert result.report["uncovered_active_seconds"] > .3


def test_postprocess_trims_only_outer_silent_margin_and_preserves_internal_boundary(tmp_path: Path) -> None:
    audio = tmp_path / "a.wav"
    write_wave(audio, ((.1, .7),))
    result = postprocess_annotations(audio, 1., (phone(.03, .4), phone(.4, .79)))
    assert result.report["passed"]
    speech = [p for p in result.annotations if not p.is_silence]
    assert .07 <= speech[0].interval.start <= .1
    assert .7 <= speech[-1].interval.end <= .73
    assert speech[0].interval.end == speech[1].interval.start == .4
    assert result.annotations[0].is_silence and result.annotations[-1].is_silence
    assert len(result.report["edits"]) == 2


def test_postprocess_rejects_silent_audio(tmp_path: Path) -> None:
    audio = tmp_path / "a.wav"
    write_wave(audio, ())
    result = postprocess_annotations(audio, 1., (phone(.1, .8),))
    assert not result.report["passed"]
    assert result.report["reason_code"] == "alignment_no_activity"


def test_postprocess_recovers_small_late_onset_without_consuming_other_phone(tmp_path: Path) -> None:
    audio = tmp_path / "a.wav"
    write_wave(audio, ((.1, .7),))
    leading = PhoneAnnotation(PhoneInterval(0., .16, ""), None, (), "", "", True)
    result = postprocess_annotations(audio, 1., (leading, phone(.16, .7)))
    assert result.report["passed"]
    assert result.annotations[0].interval.end == pytest.approx(.085)
    assert result.annotations[1].interval.start == pytest.approx(.085)


def test_postprocess_audits_single_sample_roundoff_but_rejects_large_overshoot(tmp_path: Path) -> None:
    audio = tmp_path / "a.wav"
    write_wave(audio, ((.1, .8),))
    blank = lambda end: PhoneAnnotation(PhoneInterval(.8, end, ""), None, (), "", "", True)
    result = postprocess_annotations(audio, 1., (phone(.1, .8), blank(1.00004)))
    assert result.report["passed"]
    assert result.annotations[-1].interval.end == 1.
    assert result.report["edits"][0]["reason"] == "sample_roundoff"
    with pytest.raises(ValueError, match="duration"):
        postprocess_annotations(audio, 1., (phone(.1, .8), blank(1.02)))
