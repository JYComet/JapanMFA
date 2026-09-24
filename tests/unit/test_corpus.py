from pathlib import Path

import pytest

from japanmfa.corpus import discover_utterances, load_source_text
from japanmfa.errors import StageFailure


def touch_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF")


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    return tmp_path / "corpus"


def test_duplicate_basenames_get_relative_ids(corpus: Path) -> None:
    touch_wav(corpus / "a" / "001.wav")
    touch_wav(corpus / "b" / "001.wav")

    assert [u.utterance_id for u in discover_utterances(corpus)] == ["a/001", "b/001"]


def test_source_text_preserves_original_and_normalizes_processing_copy(tmp_path: Path) -> None:
    path = tmp_path / "x.txt"
    path.write_bytes(
        b"\xef\xbb\xbf\xe4\xbb\x8a\xe6\x97\xa5\r\n\xe3\x81\xaf\xe6\x99\xb4\xe3\x82\x8c\r\n"
    )

    text = load_source_text(path)

    assert text.original == "今日\r\nは晴れ\r\n"
    assert text.processing == "今日は晴れ"
    assert text.source == "txt"


def test_source_text_nfc_normalizes_decomposed_japanese_without_changing_original(
    tmp_path: Path,
) -> None:
    path = tmp_path / "decomposed.txt"
    original = " \r\nか\u3099な\r\n"
    path.write_text(original, encoding="utf-8", newline="")

    text = load_source_text(path)

    assert text.original == original
    assert text.processing == "がな"


def test_discovery_is_deterministic_and_ignores_unsupported_extensions(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    touch_wav(corpus / "z.wav")
    touch_wav(corpus / "a" / "10.wav")
    touch_wav(corpus / "a" / "2.wav")
    (corpus / "ignored.mp3").parent.mkdir(parents=True, exist_ok=True)
    (corpus / "ignored.mp3").write_bytes(b"mp3")
    (corpus / "UPPER.WAV").write_bytes(b"wav")

    assert [u.utterance_id for u in discover_utterances(corpus)] == [
        "a/10",
        "a/2",
        "z",
    ]


def test_symlinked_audio_is_rejected_by_default(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    source = tmp_path / "source.wav"
    touch_wav(source)
    corpus.mkdir()
    link = corpus / "linked.wav"
    link.symlink_to(source)

    with pytest.raises(StageFailure, match="symlink") as exc_info:
        discover_utterances(corpus)

    assert exc_info.value.stage == "discovery"
    assert exc_info.value.reason_code == "symlink_audio"


def test_case_folded_utterance_id_collision_fails(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    touch_wav(corpus / "A.wav")
    touch_wav(corpus / "a.wav")

    with pytest.raises(StageFailure) as exc_info:
        discover_utterances(corpus)

    assert exc_info.value.stage == "discovery"
    assert exc_info.value.reason_code == "duplicate_utterance_id"


def test_discovery_associates_existing_sidecar_text(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    audio = corpus / "nested" / "line.wav"
    touch_wav(audio)
    text = audio.with_suffix(".txt")
    text.write_text("今日", encoding="utf-8")

    utterance = discover_utterances(corpus)[0]

    assert utterance.audio_path == audio
    assert utterance.text_path == text


def test_discovery_accepts_ogg_with_reference_and_rejects_duplicate_stem(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "line.ogg").write_bytes(b"OggS")
    (corpus / "line.txt").write_text("世界、大丈夫？", encoding="utf-8")
    utterance = discover_utterances(corpus)[0]
    assert utterance.utterance_id == "line"
    assert utterance.audio_path.suffix == ".ogg"
    assert utterance.text_path == corpus / "line.txt"

    touch_wav(corpus / "line.wav")
    with pytest.raises(StageFailure) as exc_info:
        discover_utterances(corpus)
    assert exc_info.value.reason_code == "duplicate_utterance_id"
