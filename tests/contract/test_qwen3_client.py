import json
import sys
from pathlib import Path

import pytest

from japanmfa.asr.qwen3 import ASRResult, Qwen3ASRClient
from japanmfa.errors import StageFailure


@pytest.fixture
def fake_worker() -> Path:
    return Path(__file__).parents[1] / "fixtures" / "bin" / "fake_qwen_worker.py"


def test_client_forces_japanese_and_preserves_order(
    fake_worker: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request_record = tmp_path / "request.json"
    monkeypatch.setenv("FAKE_QWEN_REQUEST_RECORD", str(request_record))
    client = Qwen3ASRClient(
        command=[sys.executable, str(fake_worker)], model="Qwen/Qwen3-ASR-1.7B"
    )
    paths = [tmp_path / "a.wav", tmp_path / "b.wav"]

    results = client.transcribe(paths)

    assert list(results) == paths
    assert isinstance(results[paths[0]], ASRResult)
    assert results[paths[0]].language == "Japanese"
    assert results[paths[0]].text == "今日は晴れ"
    assert results[paths[0]].model == "Qwen/Qwen3-ASR-1.7B"
    request = json.loads(request_record.read_text(encoding="utf-8"))
    assert request == {
        "model": "Qwen/Qwen3-ASR-1.7B",
        "aligner_model": "Qwen/Qwen3-ForcedAligner-0.6B",
        "language": "Japanese",
        "audio_paths": [str(path) for path in paths],
        "reference_texts": [None, None],
    }


@pytest.mark.parametrize(
    ("mode", "reason_code"),
    [
        ("malformed", "malformed_response"),
        ("duplicate", "result_coverage_mismatch"),
        ("missing", "result_coverage_mismatch"),
        ("non_japanese", "non_japanese_language"),
        ("nonzero", "worker_failed"),
    ],
)
def test_client_protocol_failures_are_typed(
    fake_worker: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    reason_code: str,
) -> None:
    monkeypatch.setenv("FAKE_QWEN_WORKER_MODE", mode)
    client = Qwen3ASRClient(command=[sys.executable, str(fake_worker)])

    with pytest.raises(StageFailure) as exc_info:
        client.transcribe([tmp_path / "a.wav", tmp_path / "b.wav"])

    assert exc_info.value.stage == "asr"
    assert exc_info.value.reason_code == reason_code


def test_client_rejects_relative_audio_paths(fake_worker: Path, tmp_path: Path) -> None:
    client = Qwen3ASRClient(command=[sys.executable, str(fake_worker)])

    with pytest.raises(StageFailure) as exc_info:
        client.transcribe([Path("relative.wav")])

    assert exc_info.value.stage == "asr"
    assert exc_info.value.reason_code == "audio_path_not_absolute"


def test_client_requests_forced_alignment_with_authoritative_japanese_text(
    fake_worker: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = tmp_path / "request.json"
    monkeypatch.setenv("FAKE_QWEN_REQUEST_RECORD", str(record))
    client = Qwen3ASRClient([sys.executable, str(fake_worker)])
    audio = tmp_path / "a.wav"

    result = client.transcribe([audio], reference_texts={audio: "今日は、晴れ。"})[audio]

    request = json.loads(record.read_text(encoding="utf-8"))
    assert request["language"] == "Japanese"
    assert request["aligner_model"] == "Qwen/Qwen3-ForcedAligner-0.6B"
    assert request["reference_texts"] == ["今日は、晴れ。"]
    assert result.alignment_text == "今日は、晴れ。"
    assert result.punctuation_timestamps[0].text == "、"
    assert result.punctuation_timestamps[0].start == 0.5
    assert result.punctuation_timestamps[0].end == 0.7
