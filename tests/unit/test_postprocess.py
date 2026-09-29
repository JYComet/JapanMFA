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
    assert not result.report["passed"]
    assert result.report["reason_code"] == "alignment_acoustic_coverage"
    assert result.report["bgm_suspects"] == []
    assert result.report["bgm_diagnostics"][0]["veto"] is False
    assert result.report["pause_acoustic_coverage"]["suspect_pauses"]


def test_postprocess_rejects_speech_hidden_in_synthetic_tail(tmp_path: Path) -> None:
    """A Qwen crop ending mid-utterance must not publish its remainder as silence."""
    from japanmfa.mfa.textgrid import MfaAlignment, MfaPhone, MfaWord

    audio = tmp_path / "truncated_qwen_crop.wav"
    write_wave(audio, ((.5, 1.35),), duration=2.)
    alignment = MfaAlignment(
        words=(MfaWord("jmfa_000000", .5, 1.),),
        phones=(MfaPhone("a", .5, 1., "jmfa_000000", False),),
        diagnostic_intervals=(),
    )
    result = postprocess_annotations(audio, 2., (phone(.5, 1.),), mfa_alignment=alignment)

    assert not result.report["passed"]
    assert result.report["reason_code"] == "alignment_acoustic_coverage"
    assert result.annotations[-1].is_silence
    assert result.annotations[-1].interval.start == 1.


def test_postprocess_allows_short_decay_in_synthetic_tail(tmp_path: Path) -> None:
    from japanmfa.mfa.textgrid import MfaAlignment, MfaPhone, MfaWord

    audio = tmp_path / "short_decay.wav"
    write_wave(audio, ((.5, 1.03),), duration=2.)
    alignment = MfaAlignment(
        words=(MfaWord("jmfa_000000", .5, 1.),),
        phones=(MfaPhone("a", .5, 1., "jmfa_000000", False),),
        diagnostic_intervals=(),
    )
    result = postprocess_annotations(audio, 2., (phone(.5, 1.),), mfa_alignment=alignment)

    assert result.report["passed"]


def test_postprocess_does_not_call_quiet_background_speech(tmp_path: Path) -> None:
    from japanmfa.mfa.textgrid import MfaAlignment, MfaPhone, MfaWord

    audio = tmp_path / "quiet_background.wav"
    samples = array.array("h", (
        int((8000 if .5 <= i / 16000 < 1.0 else 900 if 1.25 <= i / 16000 < 1.55 else 0)
            * math.sin(2 * math.pi * 200 * i / 16000))
        for i in range(2 * 16000)
    ))
    with wave.open(str(audio), "wb") as out:
        out.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        out.writeframes(samples.tobytes())
    alignment = MfaAlignment(
        words=(MfaWord("jmfa_000000", .5, 1.),),
        phones=(MfaPhone("a", .5, 1., "jmfa_000000", False),),
        diagnostic_intervals=(),
    )

    result = postprocess_annotations(audio, 2., (phone(.5, 1.),), mfa_alignment=alignment)

    assert result.report["passed"]
    assert result.report["synthetic_silence_speech_regions"] == []


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
    assert result.annotations[0].interval.end == pytest.approx(.1, abs=.01)
    assert result.annotations[1].interval.start == result.annotations[0].interval.end
    assert any(edit["reason"] == "energy_onset_pullback" for edit in result.report["edits"])


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


def test_bgm_audit_ignores_sparse_transients_in_explicit_silence() -> None:
    import numpy as np
    from japanmfa.postprocess import _bgm_suspects

    samples = np.zeros(2000, dtype=np.float32)
    samples[500:1000] = .03
    samples[1000::10] = .1
    silence = PhoneAnnotation(PhoneInterval(0., .5, ""), None, (), "", "", True)
    speech = phone(.5, 1.)
    trailing = PhoneAnnotation(PhoneInterval(1., 2., ""), None, (), "", "", True)
    suspects = _bgm_suspects(samples, 1000, (silence, speech, trailing))
    assert suspects == []


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


def test_energy_refinement_extends_vowel_into_mfa_tail_silence(tmp_path: Path) -> None:
    """A loud vowel tail assigned to explicit MFA silence must retain its speech owner."""
    from japanmfa.mfa.textgrid import MfaAlignment, MfaPhone, MfaWord

    audio = tmp_path / "tail.wav"
    samples = array.array("h", (
        int((3000 if .5 <= i / 16000 < .9 else 10000 if .9 <= i / 16000 < 1.2 else 0)
            * math.sin(2 * math.pi * 200 * i / 16000))
        for i in range(round(1.5 * 16000))
    ))
    with wave.open(str(audio), "wb") as out:
        out.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        out.writeframes(samples.tobytes())
    leading = PhoneAnnotation(PhoneInterval(0., .5, ""), None, (), "", "", True)
    vowel = phone(.5, .9)
    trailing = PhoneAnnotation(PhoneInterval(.9, 1.5, ""), None, (), "", "", True)
    alignment = MfaAlignment(
        words=(MfaWord("jmfa_000000", .5, .9),),
        phones=(MfaPhone("", 0., .5, None, True),
                MfaPhone("a", .5, .9, "jmfa_000000", False),
                MfaPhone("", .9, 1.5, None, True)),
        diagnostic_intervals=(),
    )
    result = postprocess_annotations(audio, 1.5, (leading, vowel, trailing), mfa_alignment=alignment)
    assert result.report["passed"]
    assert result.report["bgm_suspects"] == []
    assert result.annotations[1].interval.end == pytest.approx(1.2, abs=.02)
    assert result.annotations[2].interval.start == result.annotations[1].interval.end
    assert any(edit["reason"] == "energy_tail_extension" for edit in result.report["edits"])



def test_energy_refinement_scans_contiguous_fragmented_silence_on_global_frames() -> None:
    import numpy as np
    from japanmfa.postprocess import _refine_silence_phone_boundaries

    rate = 16000
    times = np.arange(int(1.5 * rate)) / rate
    audio = np.where((times >= .5) & (times < 1.2), .25 * np.sin(2 * np.pi * 200 * times), 0.0)
    leading = PhoneAnnotation(PhoneInterval(0., .5, ""), None, (), "", "", True)
    vowel = phone(.5, .9053)
    short_silence = PhoneAnnotation(PhoneInterval(.9053, .93, ""), None, (), "", "", True)
    long_silence = PhoneAnnotation(PhoneInterval(.93, 1.5, ""), None, (), "", "", True)

    refined, edits = _refine_silence_phone_boundaries(
        audio, rate, (leading, vowel, short_silence, long_silence),
    )

    assert refined[1].interval.end == pytest.approx(1.2, abs=.01)
    assert len(refined) == 3  # the fully consumed explicit fragment is removed
    assert refined[2].is_silence
    assert refined[2].interval.start == refined[1].interval.end
    assert any(edit["reason"] == "energy_tail_extension" for edit in edits)


def test_energy_refinement_stops_at_quiet_break_before_detached_burst() -> None:
    import numpy as np
    from japanmfa.postprocess import _refine_silence_phone_boundaries

    rate = 16000
    times = np.arange(int(1.5 * rate)) / rate
    active = ((times >= .5) & (times < 1.0)) | ((times >= 1.12) & (times < 1.25))
    audio = np.where(active, .25 * np.sin(2 * np.pi * 200 * times), 0.0)
    leading = PhoneAnnotation(PhoneInterval(0., .5, ""), None, (), "", "", True)
    vowel = phone(.5, .9)
    silence = PhoneAnnotation(PhoneInterval(.9, 1.5, ""), None, (), "", "", True)

    refined, edits = _refine_silence_phone_boundaries(audio, rate, (leading, vowel, silence))

    assert refined[1].interval.end == pytest.approx(1.0, abs=.01)
    assert refined[2].interval.start == refined[1].interval.end
    assert any(edit["reason"] == "energy_tail_extension" for edit in edits)


def test_energy_refinement_preserves_residual_pause_when_both_phone_edges_move() -> None:
    import numpy as np
    from japanmfa.postprocess import _refine_silence_phone_boundaries

    rate = 16000
    times = np.arange(int(2.0 * rate)) / rate
    active = ((times >= .5) & (times < 1.0)) | ((times >= 1.03) & (times < 1.45))
    audio = np.where(active, .25 * np.sin(2 * np.pi * 200 * times), 0.0)
    leading = PhoneAnnotation(PhoneInterval(0., .5, ""), None, (), "", "", True)
    first = phone(.5, .9)
    pause = PhoneAnnotation(PhoneInterval(.9, 1.12, ""), None, (), "", "", True)
    second = phone(1.12, 1.5)
    trailing = PhoneAnnotation(PhoneInterval(1.5, 2., ""), None, (), "", "", True)

    refined, edits = _refine_silence_phone_boundaries(
        audio, rate, (leading, first, pause, second, trailing),
    )

    first_row = next(item for item in refined if not item.is_silence and item.interval.start == .5)
    second_row = next(item for item in refined if not item.is_silence and item.interval.start > .9)
    residual = next(item for item in refined if item.is_silence and item.interval.start > .9)
    assert first_row.interval.end == pytest.approx(1.0, abs=.01)
    assert second_row.interval.start == pytest.approx(1.03, abs=.01)
    assert residual.interval.start == first_row.interval.end
    assert residual.interval.end == second_row.interval.start
    assert residual.interval.end - residual.interval.start == pytest.approx(.03, abs=.01)
    assert {edit["index"] for edit in edits} == {1, 3}


def test_energy_refinement_never_moves_a_speech_to_speech_edge() -> None:
    import numpy as np
    from japanmfa.postprocess import _refine_silence_phone_boundaries

    rate = 16000
    times = np.arange(rate) / rate
    audio = (.25 * np.sin(2 * np.pi * 200 * times)).astype(np.float32)
    first, second = phone(.1, .5), phone(.5, .9)

    refined, edits = _refine_silence_phone_boundaries(audio, rate, (first, second))

    assert refined == (first, second)
    assert edits == []


def test_energy_refinement_uses_synthetic_quiet_after_explicit_fragment() -> None:
    import numpy as np
    from japanmfa.postprocess import _refine_silence_phone_boundaries

    rate = 16000
    times = np.arange(int(2.0 * rate)) / rate
    audio = np.where((times >= .5) & (times < 1.54), .25 * np.sin(2 * np.pi * 200 * times), 0.0)
    leading = PhoneAnnotation(PhoneInterval(0., .5, ""), None, (), "", "", True)
    vowel = phone(.5, 1.18)
    explicit = PhoneAnnotation(PhoneInterval(1.18, 1.55, ""), None, (), "", "", True)

    refined, edits = _refine_silence_phone_boundaries(audio, rate, (leading, vowel, explicit))

    assert len(refined) == 3  # the synthetic remainder is search evidence, not a returned owner
    assert refined[1].interval.end == pytest.approx(1.54, abs=.01)
    assert refined[2].interval.start == refined[1].interval.end
    assert any(edit["reason"] == "energy_tail_extension" for edit in edits)


def test_energy_refinement_allows_bounded_slow_decay_beyond_half_second() -> None:
    import numpy as np
    from japanmfa.postprocess import _refine_silence_phone_boundaries

    rate = 16000
    times = np.arange(int(2.5 * rate)) / rate
    envelope = np.where(times < 1.2, 1.0, np.exp(-(times - 1.2) / .16))
    audio = np.where((times >= .5) & (times < 2.3), .25 * envelope * np.sin(2 * np.pi * 200 * times), 0.0)
    leading = PhoneAnnotation(PhoneInterval(0., .5, ""), None, (), "", "", True)
    vowel = phone(.5, 1.28)
    trailing = PhoneAnnotation(PhoneInterval(1.28, 2.5, ""), None, (), "", "", True)

    refined, edits = _refine_silence_phone_boundaries(audio, rate, (leading, vowel, trailing))

    assert refined[1].interval.end == pytest.approx(2.0, abs=.04)
    assert refined[2].interval.start == refined[1].interval.end
    edit = next(edit for edit in edits if edit["reason"] == "energy_tail_extension")
    assert edit["support_mode"] == "measured_decay_800ms"
    assert edit["source_pause_start"] == 1.28
    assert edit["source_pause_end"] == 2.5
    assert edit["decay_slope_per_second"] < 0
    assert edit["decay_r_squared"] >= .8
    assert edit["decay_end_to_start_ratio"] <= .1
    assert edit["decay_max_adjacent_rise_ratio"] <= 1.5


@pytest.mark.parametrize("tail", ("low_plateau", "late_step_drop"))
def test_energy_refinement_rejects_long_tail_without_continuous_decay(tail: str) -> None:
    import numpy as np
    from japanmfa.postprocess import _refine_silence_phone_boundaries

    rate = 16000
    times = np.arange(int(2.5 * rate)) / rate
    amplitude = np.zeros_like(times)
    amplitude[(times >= .5) & (times < 1.28)] = .25
    if tail == "low_plateau":
        amplitude[(times >= 1.28) & (times < 1.98)] = .10
    else:
        amplitude[(times >= 1.28) & (times < 1.78)] = .10
        amplitude[(times >= 1.78) & (times < 1.98)] = .01
    audio = amplitude * np.sin(2 * np.pi * 200 * times)
    leading = PhoneAnnotation(PhoneInterval(0., .5, ""), None, (), "", "", True)
    vowel = phone(.5, 1.28)
    trailing = PhoneAnnotation(PhoneInterval(1.28, 2.5, ""), None, (), "", "", True)

    refined, edits = _refine_silence_phone_boundaries(audio, rate, (leading, vowel, trailing))

    assert refined[1].interval.end == 1.28
    assert not edits


def test_energy_refinement_does_not_extend_long_flat_or_reattacking_tail() -> None:
    import numpy as np
    from japanmfa.postprocess import _pause_acoustic_coverage, _refine_silence_phone_boundaries

    rate = 16000
    times = np.arange(int(2.5 * rate)) / rate
    active = (times >= .5) & (times < 1.95)
    audio = np.where(active, .25 * np.sin(2 * np.pi * 200 * times), 0.0)
    leading = PhoneAnnotation(PhoneInterval(0., .5, ""), None, (), "", "", True)
    vowel = phone(.5, 1.28)
    trailing = PhoneAnnotation(PhoneInterval(1.28, 2.5, ""), None, (), "", "", True)

    refined, edits = _refine_silence_phone_boundaries(audio, rate, (leading, vowel, trailing))

    assert refined[1].interval.end == 1.28
    assert not edits

    reattack = np.where(((times >= .5) & (times < 1.45)) | ((times >= 1.55) & (times < 1.76)),
                        .25 * np.sin(2 * np.pi * 200 * times), 0.0)
    refined, edits = _refine_silence_phone_boundaries(reattack, rate, (leading, vowel, trailing))
    assert refined[1].interval.end == pytest.approx(1.45, abs=.01)
    coverage = _pause_acoustic_coverage(reattack, rate, refined)
    assert coverage["suspect_pauses"]


def test_pause_acoustic_coverage_reports_middle_island_and_source_spans() -> None:
    import numpy as np
    from japanmfa.postprocess import _pause_acoustic_coverage

    rate = 16000
    times = np.arange(2 * rate) / rate
    audio = np.where(((times >= .2) & (times < .7)) | ((times >= 1.1) & (times < 1.27)),
                     .25 * np.sin(2 * np.pi * 200 * times), 0.0)
    leading = PhoneAnnotation(PhoneInterval(0., .2, ""), None, (), "", "", True)
    first = phone(.2, .7)
    pause = PhoneAnnotation(PhoneInterval(.7, 1.4, ""), None, (), "", "", True)
    explicit = ((.75, .8),)

    report = _pause_acoustic_coverage(audio, rate, (leading, first, pause), explicit)

    assert len(report["pauses"]) == 2
    middle = report["pauses"][1]
    assert middle["active_seconds"] == pytest.approx(.17)
    assert middle["longest_active_seconds"] == pytest.approx(.17)
    assert middle["suspect"]
    assert middle["explicit_source_overlaps"] == [[.75, .8]]
    assert middle["synthetic_source_overlaps"] == [[.7, .75], [.8, 1.4]]
    assert len(report["suspect_pauses"]) == 1


def test_pause_acoustic_coverage_accepts_quiet_pause_and_flags_two_frame_edges() -> None:
    import numpy as np
    from japanmfa.postprocess import _pause_acoustic_coverage

    rate = 16000
    times = np.arange(rate) / rate
    audio = np.where(((times >= .2) & (times < .5)) | ((times >= .78) & (times < .8)),
                     .25 * np.sin(2 * np.pi * 200 * times), 0.0)
    rows = (PhoneAnnotation(PhoneInterval(0., .2, ""), None, (), "", "", True),
            phone(.2, .5), PhoneAnnotation(PhoneInterval(.5, .8, ""), None, (), "", "", True),
            phone(.8, .9), PhoneAnnotation(PhoneInterval(.9, 1., ""), None, (), "", "", True))
    report = _pause_acoustic_coverage(audio, rate, rows, ((.5, .8), (.9, 1.)))

    assert report["pauses"][0]["suspect"] is False
    assert report["pauses"][1]["active_edge"] is True
    assert report["pauses"][1]["suspect"] is True


def test_energy_refinement_pulls_back_short_missed_synthetic_leading_onset() -> None:
    import numpy as np
    from japanmfa.postprocess import _refine_silence_phone_boundaries

    rate = 16000
    times = np.arange(int(1.0 * rate)) / rate
    audio = np.where((times >= .53) & (times < .9), .25 * np.sin(2 * np.pi * 200 * times), 0.0)
    speech = phone(.56, .9)

    refined, edits = _refine_silence_phone_boundaries(audio, rate, (speech,))

    assert len(refined) == 1
    assert refined[0].interval.start == pytest.approx(.53, abs=.01)
    assert edits[0]["reason"] == "energy_synthetic_leading_onset_pullback"


def test_detached_synthetic_leading_island_is_not_pulled_into_speech(tmp_path: Path) -> None:
    from japanmfa.mfa.textgrid import MfaAlignment, MfaPhone, MfaWord

    audio = tmp_path / "detached_leading_island.wav"
    write_wave(audio, ((.2, .42), (.56, .9)))
    alignment = MfaAlignment(
        words=(MfaWord("jmfa_000000", .56, .9),),
        phones=(MfaPhone("a", .56, .9, "jmfa_000000", False),),
        diagnostic_intervals=(),
    )

    result = postprocess_annotations(audio, 1., (phone(.56, .9),), mfa_alignment=alignment)

    assert result.report["reason_code"] == "alignment_acoustic_coverage"
    assert result.annotations[1].interval.start == .56
    assert result.report["synthetic_silence_speech_regions"]
    assert not any(edit["reason"] == "energy_synthetic_leading_onset_pullback"
                   for edit in result.report["edits"])


def test_onset_refinement_uses_nearest_transition_after_multiple_bursts() -> None:
    import numpy as np
    from japanmfa.postprocess import _refine_silence_phone_boundaries

    rate = 16000
    times = np.arange(int(1.0 * rate)) / rate
    active = ((times >= .46) & (times < .49)) | ((times >= .53) & (times < .9))
    audio = np.where(active, .25 * np.sin(2 * np.pi * 200 * times), 0.0)
    speech = phone(.56, .9)

    refined, edits = _refine_silence_phone_boundaries(audio, rate, (speech,))

    assert refined[0].interval.start == pytest.approx(.53, abs=.01)
    assert edits[0]["reason"] == "energy_synthetic_leading_onset_pullback"


def test_onset_refinement_can_consume_contiguous_silence_fragments() -> None:
    import numpy as np
    from japanmfa.postprocess import _refine_silence_phone_boundaries

    rate = 16000
    times = np.arange(int(1.0 * rate)) / rate
    audio = np.where((times >= .47) & (times < .9), .25 * np.sin(2 * np.pi * 200 * times), 0.0)
    first_silence = PhoneAnnotation(PhoneInterval(0., .5, ""), None, (), "", "", True)
    second_silence = PhoneAnnotation(PhoneInterval(.5, .56, ""), None, (), "", "", True)
    speech = phone(.56, .9)

    refined, edits = _refine_silence_phone_boundaries(
        audio, rate, (first_silence, second_silence, speech),
    )

    assert len(refined) == 2
    assert refined[0].interval.end == pytest.approx(.47, abs=.01)
    assert refined[1].interval.start == refined[0].interval.end
    assert edits[0]["reason"] == "energy_onset_pullback"


def test_onset_refinement_uses_quiet_before_first_explicit_fragment() -> None:
    import numpy as np
    from japanmfa.postprocess import _refine_silence_phone_boundaries

    rate = 16000
    times = np.arange(rate) / rate
    audio = np.where((times >= .50) & (times < .9), .25 * np.sin(2 * np.pi * 200 * times), 0.0)
    silence = PhoneAnnotation(PhoneInterval(.48, .54, ""), None, (), "", "", True)
    refined, edits = _refine_silence_phone_boundaries(audio, rate, (silence, phone(.54, .9)))
    assert refined[1].interval.start == pytest.approx(.50, abs=.01)
    assert any(edit['reason'] == 'energy_onset_pullback' for edit in edits)


def test_short_fully_active_pause_extends_preceding_vowel() -> None:
    import numpy as np
    from japanmfa.postprocess import _refine_silence_phone_boundaries

    rate = 16000
    times = np.arange(rate) / rate
    audio = np.where((times >= .2) & (times < .8), .25 * np.sin(2 * np.pi * 200 * times), 0.0)
    pause = PhoneAnnotation(PhoneInterval(.5, .53, ""), None, (), "", "", True)
    refined, edits = _refine_silence_phone_boundaries(audio, rate, (phone(.2, .5), pause, phone(.53, .8)))
    assert len(refined) == 2
    assert refined[0].interval.end == pytest.approx(.53)
    assert any(edit['reason'] == 'energy_short_sp0_backward' for edit in edits)


def test_short_quiet_pause_is_not_absorbed_by_acoustic_rule() -> None:
    import numpy as np
    from japanmfa.postprocess import _refine_silence_phone_boundaries

    rate = 16000
    times = np.arange(rate) / rate
    active = ((times >= .2) & (times < .5)) | ((times >= .53) & (times < .8))
    audio = np.where(active, .25 * np.sin(2 * np.pi * 200 * times), 0.0)
    pause = PhoneAnnotation(PhoneInterval(.5, .53, ""), None, (), "", "", True)
    refined, edits = _refine_silence_phone_boundaries(audio, rate, (phone(.2, .5), pause, phone(.53, .8)))
    assert len(refined) == 3
    assert not any(edit['reason'] == 'energy_short_sp0_backward' for edit in edits)


def test_onset_refinement_sees_quiet_before_short_last_fragment_after_tail_edit() -> None:
    import numpy as np
    from japanmfa.postprocess import _refine_silence_phone_boundaries

    rate = 16000
    times = np.arange(2 * rate) / rate
    active = ((times >= .50) & (times < .82)) | ((times >= 1.68) & (times < 1.9))
    audio = np.where(active, .25 * np.sin(2 * np.pi * 200 * times), 0.0)
    first_pause = PhoneAnnotation(PhoneInterval(.77, .8, ""), None, (), "", "", True)
    last_pause = PhoneAnnotation(PhoneInterval(1.68, 1.71, ""), None, (), "", "", True)
    refined, edits = _refine_silence_phone_boundaries(
        audio, rate, (phone(.5, .77), first_pause, last_pause, phone(1.71, 1.9)))
    assert refined[-1].interval.start == pytest.approx(1.68)
    assert any(edit['reason'] == 'energy_tail_extension' for edit in edits)
    assert any(edit['reason'] == 'energy_onset_pullback' and edit['before'] == 1.71 for edit in edits)

def test_energy_refinement_does_not_bridge_large_mfa_silence_error(tmp_path: Path) -> None:
    """A separate sound burst far inside explicit silence needs a new alignment."""
    from japanmfa.mfa.textgrid import MfaAlignment, MfaPhone, MfaWord

    audio = tmp_path / "bad_alignment.wav"
    write_wave(audio, ((.5, .8), (1.15, 1.22)), duration=1.5)
    leading = PhoneAnnotation(PhoneInterval(0., 1.12, ""), None, (), "", "", True)
    vowel = phone(1.12, 1.25)
    trailing = PhoneAnnotation(PhoneInterval(1.25, 1.5, ""), None, (), "", "", True)
    alignment = MfaAlignment(
        words=(MfaWord("jmfa_000000", 1.12, 1.25),),
        phones=(MfaPhone("", 0., 1.12, None, True),
                MfaPhone("a", 1.12, 1.25, "jmfa_000000", False),
                MfaPhone("", 1.25, 1.5, None, True)),
        diagnostic_intervals=(),
    )
    result = postprocess_annotations(audio, 1.5, (leading, vowel, trailing), mfa_alignment=alignment)
    assert result.report["reason_code"] == "alignment_acoustic_coverage"
    assert result.report["bgm_suspects"]
    assert result.annotations[0].interval.end == 1.12
    assert result.annotations[1].interval.start == 1.12


def test_bgm_audit_detects_sustained_burst_hidden_by_long_silence_average() -> None:
    """Legacy 50 ms frame scan must see a speech-like island inside MFA silence."""
    import numpy as np
    from japanmfa.postprocess import _bgm_suspects

    samples = np.zeros(2000, dtype=np.float32)
    samples[500:1000] = .30
    samples[1000:1300] = .06
    leading = PhoneAnnotation(PhoneInterval(0., .5, ""), None, (), "", "", True)
    speech = phone(.5, 1.)
    trailing = PhoneAnnotation(PhoneInterval(1., 2., ""), None, (), "", "", True)
    suspects = _bgm_suspects(samples, 1000, (leading, speech, trailing))
    assert len(suspects) == 1
    assert suspects[0]["details"][0]["xmin"] == 1.
    assert suspects[0]["details"][0]["high_ratio"] >= .20


def test_postprocess_rejects_quiet_speech_island_after_last_mfa_word(tmp_path: Path) -> None:
    """A missing final word must not pass merely because its energy is below BGM's threshold."""
    from japanmfa.mfa.textgrid import MfaAlignment, MfaPhone, MfaWord

    audio = tmp_path / "omitted_tail.wav"
    samples = array.array("h", (
        int((8000 if .5 <= i / 16000 < 1.0 else 650 if 1.18 <= i / 16000 < 1.19 or 1.2 <= i / 16000 < 1.5 else 0)
            * math.sin(2 * math.pi * 200 * i / 16000))
        for i in range(2 * 16000)
    ))
    with wave.open(str(audio), "wb") as out:
        out.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        out.writeframes(samples.tobytes())
    leading = PhoneAnnotation(PhoneInterval(0., .5, ""), None, (), "", "", True)
    trailing = PhoneAnnotation(PhoneInterval(1., 2., ""), None, (), "", "", True)
    alignment = MfaAlignment(
        words=(MfaWord("jmfa_000000", .5, 1.),),
        phones=(MfaPhone("", 0., .5, None, True),
                MfaPhone("a", .5, 1., "jmfa_000000", False),
                MfaPhone("", 1., 2., None, True)),
        diagnostic_intervals=(),
    )
    result = postprocess_annotations(audio, 2., (leading, phone(.5, 1.), trailing), mfa_alignment=alignment)
    assert result.report["bgm_suspects"] == []
    assert not result.report["passed"]
    assert result.report["reason_code"] == "alignment_acoustic_coverage"
    assert result.report["unowned_speech_regions"][0]["xmin"] == pytest.approx(1.2, abs=.02)


def test_postprocess_rejects_final_voiced_vowel_placed_in_silence(tmp_path: Path) -> None:
    """A whole-word energy average must not hide a silent final vowel phone."""
    from japanmfa.mfa.textgrid import MfaAlignment, MfaPhone, MfaWord

    audio = tmp_path / "silent_final_vowel.wav"
    write_wave(audio, ((.2, .58),), duration=1.)
    leading = PhoneAnnotation(PhoneInterval(0., .2, ""), None, (), "", "", True)
    first = PhoneAnnotation(PhoneInterval(.2, .6, "a"), 0, (Mora(0, 0, "ア", "H"),), "ア", "HH", False)
    final = PhoneAnnotation(PhoneInterval(.6, .7, "e"), 0, (Mora(0, 1, "エ", "H"),), "エ", "HH", False)
    trailing = PhoneAnnotation(PhoneInterval(.7, 1., ""), None, (), "", "", True)
    alignment = MfaAlignment(
        words=(MfaWord("jmfa_000000", .2, .7),),
        phones=(MfaPhone("", 0., .2, None, True),
                MfaPhone("a", .2, .6, "jmfa_000000", False),
                MfaPhone("e", .6, .7, "jmfa_000000", False),
                MfaPhone("", .7, 1., None, True)),
        diagnostic_intervals=(),
    )
    result = postprocess_annotations(audio, 1., (leading, first, final, trailing), mfa_alignment=alignment)
    assert not result.report["passed"]
    assert result.report["reason_code"] == "phone_in_silence"
    assert result.report["low_energy_phone_issues"][0]["label"] == "e"
