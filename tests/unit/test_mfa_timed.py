from __future__ import annotations

import pytest
import wave
from pathlib import Path

from japanmfa.asr.qwen3 import Timestamp
from japanmfa.domain import Token
from japanmfa.errors import StageFailure
from japanmfa.mfa import timed
from japanmfa.mfa.timed import TimedSegment, align_timed_segments, audit_timed_alignment, annotate_timing_report, plan_timed_segments
from japanmfa.mfa.textgrid import MfaAlignment, MfaWord


def _token(index: int, start: int, end: int, surface: str) -> Token:
    return Token(index, start, end, surface, ("名詞",), surface, "sudachi")


def test_qwen_words_bound_mfa_at_token_boundaries() -> None:
    # 0922jap 0060: whole-utterance MFA put 世界 into the quiet gap after 1.2 s.
    text = "世界、大丈夫？"
    tokens = (_token(0, 0, 2, "世界"), _token(1, 3, 6, "大丈夫"))
    timestamps = (Timestamp("世界", 0.48, 1.20), Timestamp("大丈夫", 2.00, 2.88))

    segments = plan_timed_segments(text, timestamps, tokens, 3.4131875)

    assert [(s.start, s.end, s.first_token, s.last_token) for s in segments] == [
        (0.48, 1.20, 0, 1), (2.00, 2.88, 1, 2)
    ]


def test_adjacent_qwen_words_also_bound_mfa() -> None:
    text = "世界大丈夫"
    tokens = (_token(0, 0, 2, "世界"), _token(1, 2, 5, "大丈夫"))
    timestamps = (Timestamp("世界", 0.2, 0.8), Timestamp("大丈夫", 0.8, 1.5))

    segments = plan_timed_segments(text, timestamps, tokens, 2.0)

    assert [(s.start, s.end, s.first_token, s.last_token) for s in segments] == [
        (0.2, 0.8, 0, 1), (0.8, 1.5, 1, 2),
    ]


def test_zero_width_qwen_item_does_not_create_unreliable_mfa_cut() -> None:
    text = "寒気がして"
    tokens = (_token(0, 0, 2, "寒気"), _token(1, 2, 3, "が"), _token(2, 3, 4, "し"), _token(3, 4, 5, "て"))
    timestamps = (
        Timestamp("寒気", 2.08, 2.72), Timestamp("が", 2.72, 2.72),
        Timestamp("し", 2.96, 3.12), Timestamp("て", 3.20, 3.28),
    )

    segments = plan_timed_segments(text, timestamps, tokens, 4.0)

    assert segments == (TimedSegment(2.08, 3.28, 0, 4, 2.08, 3.28),)


def test_short_qwen_word_never_merges_across_a_long_silence() -> None:
    text = "してうわ"
    tokens = (_token(0, 0, 1, "し"), _token(1, 1, 2, "て"), _token(2, 2, 4, "うわ"))
    timestamps = (
        Timestamp("し", 2.96, 3.12), Timestamp("て", 3.2, 3.28),
        Timestamp("うわ", 5.12, 5.28),
    )

    segments = plan_timed_segments(text, timestamps, tokens, 6.0)

    assert [(s.first_token, s.last_token) for s in segments] == [(0, 2), (2, 3)]
    assert segments[0].end < segments[1].start
    assert segments[1].anchor_start == 5.12
    assert segments[1].anchor_end == 5.28


def test_short_island_gets_context_without_changing_qwen_anchor() -> None:
    text = "はぁご飯"
    tokens = (_token(0, 0, 2, "はぁ"), _token(1, 2, 4, "ご飯"))
    timestamps = (Timestamp("はぁ", 0.48, 0.56), Timestamp("ご飯", 2.08, 2.56))

    segments = plan_timed_segments(text, timestamps, tokens, 3.0)

    assert segments == (
        TimedSegment(0.0, 1.16, 0, 1, 0.48, 0.56),
        TimedSegment(2.08, 2.56, 1, 2, 2.08, 2.56),
    )


def test_short_qwen_word_joins_neighbor_inside_one_speech_island() -> None:
    text = "目の前がぐるぐるし"
    tokens = (
        _token(0, 0, 1, "目"), _token(1, 1, 2, "の"), _token(2, 2, 3, "前"),
        _token(3, 3, 4, "が"), _token(4, 4, 8, "ぐるぐる"), _token(5, 8, 9, "し"),
    )
    timestamps = (
        Timestamp("目", 0.48, 0.56), Timestamp("の", 0.56, 0.96),
        Timestamp("前", 1.04, 1.44), Timestamp("が", 1.44, 1.6),
        Timestamp("ぐるぐる", 1.68, 2.56), Timestamp("し", 2.56, 2.8),
    )

    segments = plan_timed_segments(text, timestamps, tokens, 3.0)

    assert [(s.start, s.end, s.first_token, s.last_token) for s in segments] == [
        (0.48, 1.44, 0, 3), (1.44, 2.8, 3, 6),
    ]


def test_single_qwen_group_is_cropped_and_audited() -> None:
    segments = plan_timed_segments(
        "いいね", (Timestamp("いいね", 0.2, 0.88),),
        (_token(0, 0, 3, "いいね"),), 1.6,
    )
    assert segments == (TimedSegment(0.2, 0.88, 0, 1, 0.2, 0.88),)
    alignment = MfaAlignment((MfaWord("jmfa_000000", 0.21, 1.14),), (), ())
    assert audit_timed_alignment(segments, alignment) == [
        {
            "segment": 0, "edge": "end", "qwen_seconds": 0.88,
            "mfa_seconds": 1.14, "difference_seconds": 0.26,
        }
    ]


def test_qwen_crop_expands_only_when_adjacent_speech_continues(tmp_path: Path) -> None:
    import array
    import math

    audio = tmp_path / "working.wav"
    samples = array.array("h", (
        int((8000 if .55 <= i / 16000 < 1.15 or 1.85 <= i / 16000 < 3.24
             else 900 if 1.3 <= i / 16000 < 1.6 else 0)
            * math.sin(2 * math.pi * 200 * i / 16000))
        for i in range(round(3.8 * 16000))
    ))
    with wave.open(str(audio), "wb") as stream:
        stream.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        stream.writeframes(samples.tobytes())
    segments = (
        TimedSegment(.56, 1.2, 0, 1, .56, 1.2),
        TimedSegment(1.92, 2.88, 1, 5, 1.92, 2.88),
    )

    expanded = timed.expand_timed_segments_with_audio(segments, audio)

    assert (expanded[0].start, expanded[0].end) == (.56, 1.2)
    assert (expanded[1].start, expanded[1].end) == (1.75, 3.36)
    assert expanded[1].acoustic_start_limit == pytest.approx(1.85)
    assert expanded[1].acoustic_end_limit == pytest.approx(3.24)


def _write_profile_wav(path: Path, profiles: tuple[tuple[float, float, int], ...], duration: float) -> None:
    """Write a 16 kHz tone whose amplitude changes at exact 10 ms boundaries."""
    import array
    import math

    samples = array.array("h")
    for i in range(round(duration * 16000)):
        seconds = i / 16000
        amplitude = next((value for start, end, value in profiles if start <= seconds < end), 0)
        samples.append(int(amplitude * math.sin(2 * math.pi * 200 * seconds)))
    with wave.open(str(path), "wb") as stream:
        stream.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        stream.writeframes(samples.tobytes())


@pytest.mark.parametrize(("anchor", "tail_end"), ((.88, 1.10), (.56, 1.13)))
def test_qwen_end_support_includes_connected_weak_decay(
    tmp_path: Path, anchor: float, tail_end: float,
) -> None:
    audio = tmp_path / "weak-decay.wav"
    decay_start = max(anchor + .08, tail_end - .20)
    _write_profile_wav(audio, ((anchor, decay_start, 8000), (decay_start, tail_end, 1000)), 1.6)
    segment = TimedSegment(anchor, anchor, 0, 1, anchor, anchor)

    expanded = timed.expand_timed_segments_with_audio((segment,), audio)[0]

    assert expanded.acoustic_end_limit == pytest.approx(tail_end)
    assert expanded.end >= tail_end


def test_qwen_end_support_stops_at_quiet_break_before_detached_island(tmp_path: Path) -> None:
    audio = tmp_path / "detached-island.wav"
    _write_profile_wav(audio, ((.56, .66, 8000), (.66, .70, 1000), (.78, .95, 8000)), 1.2)
    segment = TimedSegment(.56, .56, 0, 1, .56, .56)

    expanded = timed.expand_timed_segments_with_audio((segment,), audio)[0]

    assert expanded.acoustic_end_limit == pytest.approx(.70)
    assert expanded.end <= .78


def test_qwen_end_support_does_not_validate_decay_without_quiet_confirmation(tmp_path: Path) -> None:
    audio = tmp_path / "long-weak-noise.wav"
    _write_profile_wav(audio, ((.56, .66, 8000), (.66, .94, 1000)), 1.2)
    segment = TimedSegment(.56, .56, 0, 1, .56, .56)

    expanded = timed.expand_timed_segments_with_audio((segment,), audio)[0]

    assert expanded.acoustic_end_limit == pytest.approx(.66)


def test_qwen_decay_support_respects_neighbor_midpoint(tmp_path: Path) -> None:
    audio = tmp_path / "neighbor-bound.wav"
    _write_profile_wav(audio, ((.56, .66, 8000), (.66, .83, 1000), (.90, 1.10, 8000)), 1.3)
    segments = (
        TimedSegment(.56, .56, 0, 1, .56, .56),
        TimedSegment(.90, 1.10, 1, 2, .90, 1.10),
    )

    expanded = timed.expand_timed_segments_with_audio(segments, audio)

    assert expanded[0].end <= .73
    assert expanded[0].acoustic_end_limit <= .73


def test_qwen_crop_padding_stops_before_a_separate_sound(tmp_path: Path) -> None:
    import array
    import math

    audio = tmp_path / "working.wav"
    samples = array.array("h", (
        int((8000 if .5 <= i / 16000 < 1.0 or 1.03 <= i / 16000 < 1.2 else 0)
            * math.sin(2 * math.pi * 200 * i / 16000))
        for i in range(round(1.5 * 16000))
    ))
    with wave.open(str(audio), "wb") as stream:
        stream.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        stream.writeframes(samples.tobytes())

    expanded = timed.expand_timed_segments_with_audio(
        (TimedSegment(.5, .8, 0, 1, .5, .8),), audio,
    )

    assert expanded[0].acoustic_end_limit == pytest.approx(1.0)
    assert expanded[0].end <= 1.03


def test_qwen_crop_retains_quiet_confirmed_tail_when_anchor_energy_is_below_speech_floor(
    tmp_path: Path,
) -> None:
    audio = tmp_path / "weak-at-anchor.wav"
    _write_profile_wav(audio, ((.50, 1.00, 8000), (1.00, 1.10, 600)), 1.6)
    segment = TimedSegment(.50, 1.00, 0, 1, .50, 1.00)

    expanded = timed.expand_timed_segments_with_audio((segment,), audio)[0]

    assert expanded.anchor_end == 1.00
    assert expanded.acoustic_end_limit == pytest.approx(1.10, abs=.01)
    assert expanded.end >= 1.20


def test_qwen_crop_weak_tail_does_not_cross_quiet_to_detached_sound(tmp_path: Path) -> None:
    audio = tmp_path / "weak-then-island.wav"
    _write_profile_wav(
        audio, ((.50, 1.00, 8000), (1.00, 1.10, 600), (1.20, 1.36, 8000)), 1.6,
    )
    segment = TimedSegment(.50, 1.00, 0, 1, .50, 1.00)

    expanded = timed.expand_timed_segments_with_audio((segment,), audio)[0]

    assert expanded.acoustic_end_limit == pytest.approx(1.10, abs=.01)
    assert expanded.end <= 1.20  # end is exclusive when the crop is written


def test_qwen_crop_keeps_one_active_frame_after_ctc_end_for_quiet_confirmation(
    tmp_path: Path,
) -> None:
    audio = tmp_path / "one-frame-tail.wav"
    _write_profile_wav(audio, ((.50, 1.00, 8000), (1.00, 1.01, 600)), 1.6)
    segment = TimedSegment(.50, 1.00, 0, 1, .50, 1.00)

    expanded = timed.expand_timed_segments_with_audio((segment,), audio)[0]

    assert expanded.acoustic_end_limit == pytest.approx(1.01, abs=.01)
    assert expanded.end >= 1.10


def test_padding_does_not_make_unsupported_qwen_drift_acceptable() -> None:
    segments = (TimedSegment(.5, 1.12, 0, 1, .5, .8, None, 1.0),)
    alignment = MfaAlignment((MfaWord("jmfa_000000", .5, 1.04),), (), ())
    report: dict[str, object] = {"passed": True, "reason_code": None}

    issues = audit_timed_alignment(segments, alignment)
    annotate_timing_report(report, issues)

    assert len(issues) == 1
    assert "supported_by_audio" not in issues[0]
    assert report["passed"] is False
    assert report["reason_code"] == "timestamp_mfa_disagreement"


def test_acoustically_supported_qwen_tail_disagreement_remains_visible_but_can_pass() -> None:
    segments = (
        TimedSegment(.56, 1.2, 0, 1, .56, 1.2),
        TimedSegment(1.75, 3.36, 1, 5, 1.92, 2.88, 1.85, 3.24),
    )
    alignment = MfaAlignment((
        MfaWord("jmfa_000000", .56, 1.17),
        MfaWord("jmfa_000001", 1.86, 2.3),
        MfaWord("jmfa_000002", 2.3, 2.58),
        MfaWord("jmfa_000003", 2.58, 2.77),
        MfaWord("jmfa_000004", 2.77, 3.1),
    ), (), ())
    report: dict[str, object] = {"passed": True, "reason_code": None}

    issues = audit_timed_alignment(segments, alignment)
    annotate_timing_report(report, issues)

    assert len(issues) == 1
    assert issues[0]["edge"] == "end"
    assert issues[0]["supported_by_audio"] is True
    assert report["passed"] is True
    assert report["timestamp_alignment"]["issues"] == issues


def test_mismatched_qwen_text_cannot_silently_anchor_mfa() -> None:
    with pytest.raises(StageFailure) as error:
        plan_timed_segments("世界", (Timestamp("世間", 0.4, 1.2),), (_token(0, 0, 2, "世界"),), 2.0)

    assert (error.value.stage, error.value.reason_code) == ("mfa", "timestamp_text_mismatch")


def test_missing_native_qwen_timestamps_fail_closed() -> None:
    with pytest.raises(StageFailure) as error:
        plan_timed_segments("世界", (), (_token(0, 0, 2, "世界"),), 2.0)
    assert (error.value.stage, error.value.reason_code) == ("mfa", "timestamps_missing")


def test_segmented_mfa_uses_timestamp_crops_and_restores_global_times(tmp_path: Path) -> None:
    audio = tmp_path / "working.wav"
    with wave.open(str(audio), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(b"\x00\x00" * (16000 * 4))
    dictionary = tmp_path / "dictionary.dict"
    dictionary.write_text("jmfa_000000 k\njmfa_000001 a\n", encoding="utf-8")

    class RecordingMfa:
        def __init__(self) -> None:
            self.inputs: list[tuple[str, int]] = []

        def align(self, corpus_dir: Path, _dictionary: Path, output_dir: Path, _work_dir: Path) -> Path:
            lab = next(corpus_dir.glob("*.lab"))
            alias = lab.read_text(encoding="utf-8").strip()
            with wave.open(str(next(corpus_dir.glob("*.wav"))), "rb") as stream:
                self.inputs.append((alias, stream.getnframes()))
            output_dir.mkdir(parents=True)
            grid = output_dir / "aligned.TextGrid"
            grid.write_text(f'''File type = "ooTextFile"
Object class = "TextGrid"
xmin = 0
xmax = 2
tiers? <exists>
size = 2
item []:
    item [1]:
        class = "IntervalTier"
        name = "words"
        xmin = 0
        xmax = 2
        intervals: size = 1
        intervals [1]:
            xmin = 0.4
            xmax = 0.8
            text = "{alias}"
    item [2]:
        class = "IntervalTier"
        name = "phones"
        xmin = 0
        xmax = 2
        intervals: size = 1
        intervals [1]:
            xmin = 0.4
            xmax = 0.8
            text = "a"
''', encoding="utf-8")
            return grid

    runner = RecordingMfa()
    alignment, grids = align_timed_segments(
        (TimedSegment(0.0, 1.6, 0, 1), TimedSegment(1.6, 4.0, 1, 2)),
        audio, "sample", ("jmfa_000000", "jmfa_000001"), dictionary,
        tmp_path / "mfa", runner, frozenset({"", "sil"}),
    )

    assert runner.inputs == [("jmfa_000000", 25600), ("jmfa_000001", 38400)]
    assert [(word.alias, round(word.start, 2), round(word.end, 2)) for word in alignment.words] == [
        ("jmfa_000000", 0.4, 0.8), ("jmfa_000001", 2.0, 2.4)
    ]
    assert len(grids) == 2


def test_adjacent_crops_do_not_overlap_from_float_roundoff(tmp_path: Path) -> None:
    audio = tmp_path / "working.wav"
    with wave.open(str(audio), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(b"\x00\x00" * (16000 * 6))

    class ExactCropMfa:
        def align(self, corpus_dir: Path, _dictionary: Path, output_dir: Path, _work_dir: Path) -> Path:
            alias = next(corpus_dir.glob("*.lab")).read_text(encoding="utf-8").strip()
            with wave.open(str(next(corpus_dir.glob("*.wav"))), "rb") as stream:
                duration = stream.getnframes() / stream.getframerate()
            output_dir.mkdir(parents=True)
            grid = output_dir / "aligned.TextGrid"
            grid.write_text(f'''File type = "ooTextFile"
Object class = "TextGrid"
xmin = 0
xmax = {duration}
tiers? <exists>
size = 2
item []:
    item [1]:
        class = "IntervalTier"
        name = "words"
        xmin = 0
        xmax = {duration}
        intervals: size = 1
        intervals [1]:
            xmin = 0
            xmax = {duration}
            text = "{alias}"
    item [2]:
        class = "IntervalTier"
        name = "phones"
        xmin = 0
        xmax = {duration}
        intervals: size = 1
        intervals [1]:
            xmin = 0
            xmax = {duration}
            text = "a"
''', encoding="utf-8")
            return grid

    alignment, _grids = align_timed_segments(
        (TimedSegment(4.08, 4.64, 0, 1), TimedSegment(4.64, 5.36, 1, 2)),
        audio, "sample", ("jmfa_000000", "jmfa_000001"), tmp_path / "dictionary.dict",
        tmp_path / "mfa", ExactCropMfa(), frozenset({"", "sil"}),
    )

    assert alignment.phones[0].end <= alignment.phones[1].start


def test_qwen_anchor_audit_identifies_unaligned_0060_word_tail() -> None:
    text = "世界、大丈夫？"
    tokens = (_token(0, 0, 2, "世界"), _token(1, 3, 6, "大丈夫"))
    timestamps = (Timestamp("世界", 0.48, 1.20), Timestamp("大丈夫", 2.00, 2.88))
    segments = plan_timed_segments(text, timestamps, tokens, 3.4131875)
    alignment = MfaAlignment(
        (MfaWord("jmfa_000000", 0.52, 1.23), MfaWord("jmfa_000001", 1.98, 2.56)), (), ()
    )

    issues = audit_timed_alignment(segments, alignment)

    assert len(issues) == 1
    assert issues[0]["segment"] == 1
    assert issues[0]["edge"] == "end"
    assert issues[0]["difference_seconds"] == -0.32


def test_timing_disagreement_reclassifies_bgm_claim_without_ignoring_failure() -> None:
    report: dict[str, object] = {"passed": False, "reason_code": "bgm_suspect"}
    issues = [{"segment": 1, "edge": "end", "difference_seconds": -0.32}]

    annotate_timing_report(report, issues)

    assert report["reason_code"] == "timestamp_mfa_disagreement"
    assert report["acoustic_reason_code"] == "bgm_suspect"
    assert report["passed"] is False
    assert report["timestamp_alignment"]["issues"] == issues


def test_timed_mfa_rejects_symlinked_segment_root_before_writing(tmp_path: Path) -> None:
    audio = tmp_path / "audio.wav"
    with wave.open(str(audio), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(b"\x00\x00" * 16000)
    outside = tmp_path / "outside"
    outside.mkdir()
    mfa_root = tmp_path / "mfa"
    mfa_root.mkdir()
    (mfa_root / "segments").symlink_to(outside, target_is_directory=True)

    class UnusedMfa:
        def align(self, *args: object) -> Path:
            raise AssertionError("MFA must not run through a symlinked output root")

    with pytest.raises(StageFailure) as error:
        align_timed_segments(
            (TimedSegment(0.0, 1.0, 0, 1),), audio, "sample", ("jmfa_000000",),
            tmp_path / "dictionary.dict", mfa_root, UnusedMfa(), frozenset({""}),
        )

    assert error.value.reason_code == "path_ownership_invalid"
    assert list(outside.iterdir()) == []
