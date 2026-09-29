import pytest

from japanmfa.asr.timestamps import clean_asr_text, project_timestamps


def test_clean_asr_text_removes_markup_and_symbols_but_keeps_japanese_punctuation():
    assert clean_asr_text("<|audio|>こんにちは、世界！😊<sp1>\n") == "こんにちは、世界！"


def test_project_timestamps_preserves_punctuation_gap_and_lexical_surface():
    lexical, punctuation = project_timestamps(
        "こんにちは、世界！",
        [
            {"text": "こんにちは", "start_time": 0.1, "end_time": 0.6},
            {"text": "世界", "start_time": 0.9, "end_time": 1.3},
        ],
    )
    assert lexical == [
        {"text": "こんにちは", "start": 0.1, "end": 0.6},
        {"text": "世界", "start": 0.9, "end": 1.3},
    ]
    assert punctuation == [
        {"text": "、", "start": 0.6, "end": 0.9, "source": "lexical_gap"},
        {"text": "！", "start": 1.3, "end": 1.3, "source": "boundary_point"},
    ]


def test_project_timestamps_rejects_lexical_mismatch():
    with pytest.raises(ValueError, match="expected='今日' got='明日'"):
        project_timestamps("今日は晴れ。", [{"text": "明日", "start_time": 0.0, "end_time": 0.5}])


def test_project_timestamps_ignores_punctuation_only_model_items():
    lexical, punctuation = project_timestamps(
        "さ、Let's go!",
        [
            {"text": "さ", "start_time": 0.48, "end_time": 0.72},
            {"text": "Let", "start_time": 1.2, "end_time": 1.44},
            {"text": "'", "start_time": 1.44, "end_time": 1.44},
            {"text": "s", "start_time": 1.68, "end_time": 1.84},
            {"text": "go", "start_time": 1.84, "end_time": 2.56},
        ],
    )

    assert [item["text"] for item in lexical] == ["さ", "Let", "s", "go"]
    assert any(item["text"] == "'" for item in punctuation)


def test_project_timestamps_matches_fullwidth_digit_without_changing_source_surface():
    lexical, _ = project_timestamps(
        "５時です。",
        [
            {"text": "5", "start_time": 0.1, "end_time": 0.3},
            {"text": "時", "start_time": 0.3, "end_time": 0.5},
            {"text": "です", "start_time": 0.5, "end_time": 0.7},
        ],
    )

    assert lexical[0] == {"text": "５", "start": 0.1, "end": 0.3}


def test_project_timestamps_accepts_native_one_audio_batch():
    class Result:
        items = [{"text": "今日", "start_time": 0.1, "end_time": 0.4}]

    lexical, punctuation = project_timestamps("今日。", [Result()])
    assert lexical[0]["text"] == "今日"
    assert punctuation[0]["start"] == punctuation[0]["end"] == 0.4


def test_project_timestamps_marks_internal_punctuation_as_uncertain_span():
    lexical, punctuation = project_timestamps(
        "うぅ～ん……",
        [{"text": "うぅ～ん", "start_time": 0.1, "end_time": 1.0}],
    )

    assert lexical == [{"text": "うぅ～ん", "start": 0.1, "end": 1.0}]
    assert punctuation == [
        {"text": "～", "start": 0.1, "end": 1.0, "source": "lexical_span"},
        {"text": "……", "start": 1.0, "end": 1.0, "source": "boundary_point"},
    ]
