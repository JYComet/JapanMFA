import array
import math
import wave
from pathlib import Path

import pytest

from japanmfa.domain import Mora, PhoneAnnotation, PhoneInterval
from japanmfa.postprocess import (
    _detect_silence_at_beginning_vec,
    _detect_silence_at_end_vec,
    normalize_start_end_silence,
    search_silence_ranges,
    trim_excessive_silence,
    postprocess_annotations,
)


def write_wave(path: Path, regions: tuple[tuple[float, float], ...], duration: float = 1.0) -> None:
    samples = array.array("h", (int(8000 * math.sin(2 * math.pi * 200 * i / 16000)) if any(a <= i / 16000 < b for a, b in regions) else 0 for i in range(round(duration * 16000))))
    with wave.open(str(path), "wb") as out:
        out.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        out.writeframes(samples.tobytes())


def phone(start: float, end: float) -> PhoneAnnotation:
    return PhoneAnnotation(PhoneInterval(start, end, "a"), 0, (Mora(0, 0, "ア", "H"),), "ア", "HH", False)


def test_postprocess_keeps_synthetic_gap_bgm_diagnostic_only(tmp_path: Path) -> None:
    audio = tmp_path / "a.wav"
    write_wave(audio, ((.05, .4), (.7, .85)))
    result = postprocess_annotations(audio, 1., (phone(.68, .9),))
    assert result.report["passed"]
    assert result.report["bgm_suspects"] == []
    assert result.report["bgm_diagnostics"][0]["veto"] is False


def test_postprocess_trims_only_outer_silent_margin_and_preserves_internal_boundary(tmp_path: Path) -> None:
    audio = tmp_path / "a.wav"
    write_wave(audio, ((.1, .7),))
    result = postprocess_annotations(audio, 1., (phone(.03, .4), phone(.4, .79)))
    assert result.report["passed"]
    speech = [p for p in result.annotations if not p.is_silence]
    assert speech[0].interval.start == .03
    assert speech[-1].interval.end == .79
    assert speech[0].interval.end == speech[1].interval.start == .4
    assert result.annotations[0].is_silence and result.annotations[-1].is_silence
    assert result.report["edits"] == []


def test_postprocess_rejects_silent_audio(tmp_path: Path) -> None:
    audio = tmp_path / "a.wav"
    write_wave(audio, ())
    result = postprocess_annotations(audio, 1., (phone(.1, .8),))
    assert result.report["passed"]


def test_postprocess_recovers_small_late_onset_without_consuming_other_phone(tmp_path: Path) -> None:
    audio = tmp_path / "a.wav"
    write_wave(audio, ((.1, .7),))
    leading = PhoneAnnotation(PhoneInterval(0., .16, ""), None, (), "", "", True)
    result = postprocess_annotations(audio, 1., (leading, phone(.16, .7)))
    assert result.report["passed"]
    assert result.annotations[0].interval.end == .16
    assert result.annotations[1].interval.start == .16


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


def test_upstream_trim_functions_preserve_native_rate_and_tail_arithmetic() -> None:
    import numpy as np

    audio = np.concatenate([np.zeros(1600), np.ones(16000), np.zeros(3200)]).astype(np.float32)
    assert _detect_silence_at_beginning_vec(audio, 16000, silence_threshold=.001, frame_length=1024) == pytest.approx(.064)
    assert _detect_silence_at_end_vec(audio, 16000, silence_threshold=.001, frame_length=1024) == pytest.approx(.128)
    trimmed = trim_excessive_silence(audio, 16000, max_silence_sec=.1, sil_vol_threshold=.001, sil_len_threshold=.08)
    assert len(trimmed) == 1600 + 16000 + 1600
    normalized = normalize_start_end_silence(audio, 16000, target_silence_sec=.05, silence_threshold=.001, frame_length=1024)
    assert normalized.dtype == np.float32


def test_upstream_search_silence_ranges_reports_sample_ranges() -> None:
    import numpy as np

    audio = np.concatenate([np.zeros(1600), np.ones(3200), np.zeros(1600)]).astype(np.float32)
    assert search_silence_ranges(audio, 16000, sil_vol_threshold=.001, sil_len_threshold=.08) == [[0, 1600], [4800, 6400]]


def test_postprocess_report_exposes_separate_upstream_qc_sections(tmp_path: Path) -> None:
    audio = tmp_path / "a.wav"
    write_wave(audio, ((.1, .7),))
    result = postprocess_annotations(audio, 1., (phone(.1, .7),))
    assert set(("structural_issues", "short_phone_issues", "bgm_suspects", "word_energy_audit", "blocked_upstream_capabilities")) <= set(result.report)


@pytest.mark.parametrize(("seconds", "expected"), ((.014999, True), (.015, False), (.015001, False)))
def test_short_phone_qc_uses_integer_microsecond_boundary(tmp_path: Path, seconds: float, expected: bool) -> None:
    audio = tmp_path / "a.wav"
    write_wave(audio, ((0., 1.),))
    result = postprocess_annotations(audio, 1., (phone(0., seconds), phone(seconds, 1.)))
    assert bool(result.report["short_phone_issues"]) is expected


def test_bgm_audit_uses_explicit_silence_frames_and_nonzero_energy() -> None:
    import numpy as np
    from japanmfa.postprocess import _bgm_suspects

    samples = np.zeros(2000, dtype=np.float32)
    samples[500:1000] = .03
    samples[1000::10] = .1
    silence = PhoneAnnotation(PhoneInterval(0., .5, ""), None, (), "", "", True)
    speech = phone(.5, 1.)
    trailing = PhoneAnnotation(PhoneInterval(1., 2., ""), None, (), "", "", True)
    suspects = _bgm_suspects(samples, 1000, (silence, speech, trailing))
    assert len(suspects) == 1
    assert suspects[0]["noise_floor"] == pytest.approx(1e-6)


def test_word_energy_frames_are_global_10ms_float32_spans() -> None:
    import numpy as np
    from japanmfa.postprocess import _rms_frames_in_span, _word_energy_noise_model

    values, spans = _rms_frames_in_span(np.arange(100, dtype=np.float32) / 100, 1000, .004, .021)
    assert values.dtype == np.float32
    assert values.tolist() == pytest.approx([.14781746])
    assert spans == [(.01, .02)]
    model = _word_energy_noise_model(np.zeros(1000, dtype=np.float32), 1000, ())
    assert model["threshold"] == pytest.approx(1.999999995e-6)


def test_word_energy_keeps_jmfa_aliases_in_japanese_audit(tmp_path: Path) -> None:
    from japanmfa.mfa.textgrid import MfaAlignment, MfaPhone, MfaWord

    audio = tmp_path / "silent.wav"
    write_wave(audio, ())
    alignment = MfaAlignment(
        words=(MfaWord("jmfa_000000", .1, .3), MfaWord("jmfa_000001", .35, .55),
               MfaWord("jmfa_000002", .6, .8)),
        phones=(MfaPhone("a", .1, .3, "jmfa_000000", False),
                MfaPhone("a", .35, .55, "jmfa_000001", False),
                MfaPhone("a", .6, .8, "jmfa_000002", False)),
        diagnostic_intervals=(),
    )
    result = postprocess_annotations(audio, 1., (phone(.1, .8),), mfa_alignment=alignment)
    items = result.report["word_energy_audit"]["items"]
    assert items[1]["classification"] == "true_low_energy"
    assert items[1]["lineage"]["source_phone_count"] == 1


def test_discontinuity_collector_adapts_phone_annotations() -> None:
    from japanmfa.postprocess import _collect_tier_discontinuities
    first = phone(.0, .5)
    second = phone(.5, .8)
    assert _collect_tier_discontinuities((first, second), 1.0)[-1]["reason"] == "tail_gap"
    assert _collect_tier_discontinuities((phone(.0, .6), phone(.5, .8)), 1.0)[0]["reason"] == "overlap"
    assert _collect_tier_discontinuities((first, second), .8) == []


@pytest.mark.parametrize(("start", "end", "expected"), ((.00000049, .01500049, False), (.0, .015, False), (.0, .015001, False)))
def test_short_phone_qc_serializes_endpoints_before_subtraction(start: float, end: float, expected: bool) -> None:
    from japanmfa.postprocess import _phone_duration_qc_issues
    assert bool(_phone_duration_qc_issues((phone(start, end),))) is expected
