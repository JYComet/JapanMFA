import sys
import types
from pathlib import Path

import japanmfa.asr.worker as worker
from japanmfa.asr.worker import transcribe_request


class FakeTranscription:
    def __init__(self, text: str) -> None:
        self.language = "Japanese"
        self.text = text


class FakeModel:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def transcribe(self, **kwargs: object) -> list[FakeTranscription]:
        self.calls.append(kwargs)
        return [
            FakeTranscription("今日は晴れ" if i == 0 else "明日も晴れ")
            for i, _path in enumerate(kwargs["audio"])
        ]


def test_transcribe_request_locks_japanese_and_disables_timestamps() -> None:
    model = FakeModel()
    request = {
        "model": "Qwen/Qwen3-ASR-1.7B",
        "language": "Japanese",
        "audio_paths": ["/abs/a.wav", "/abs/b.wav"],
    }

    response = transcribe_request(request, lambda model_name: model)

    assert response == {
        "results": [
            {"audio_path": "/abs/a.wav", "language": "Japanese", "text": "今日は晴れ"},
            {"audio_path": "/abs/b.wav", "language": "Japanese", "text": "明日も晴れ"},
        ]
    }
    assert model.calls == [
        {
            "audio": ["/abs/a.wav", "/abs/b.wav"],
            "language": ["Japanese", "Japanese"],
            "return_time_stamps": False,
        }
    ]


def test_transcribe_request_passes_model_name_to_factory() -> None:
    model = FakeModel()
    model_names: list[str] = []

    def factory(model_name: str) -> FakeModel:
        model_names.append(model_name)
        return model

    transcribe_request(
        {
            "model": "Qwen/custom",
            "language": "Japanese",
            "audio_paths": ["/abs/a.wav"],
        },
        factory,
    )

    assert model_names == ["Qwen/custom"]


def _install_fake_qwen_runtime(monkeypatch, *, cuda: bool):
    calls: list[tuple[str, dict[str, object]]] = []

    class FakeQwenModel:
        @classmethod
        def from_pretrained(cls, model_name: str, **kwargs: object) -> object:
            calls.append((model_name, kwargs))
            return cls()

    monkeypatch.setitem(
        sys.modules,
        "torch",
        types.SimpleNamespace(
            bfloat16="bf16",
            float32="fp32",
            cuda=types.SimpleNamespace(is_available=lambda: cuda),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "qwen_asr",
        types.SimpleNamespace(Qwen3ASRModel=FakeQwenModel),
    )
    return calls, FakeQwenModel


def test_load_model_uses_cuda_when_available_without_forced_aligner(monkeypatch) -> None:
    calls, fake_model = _install_fake_qwen_runtime(monkeypatch, cuda=True)

    model = worker._load_model("Qwen/custom")

    assert isinstance(model, fake_model)
    assert calls == [
        (
            "Qwen/custom",
            {
                "dtype": "bf16",
                "device_map": "cuda:0",
                "local_files_only": True,
                "max_inference_batch_size": 32,
                "max_new_tokens": 256,
            },
        )
    ]


def test_load_model_prefers_explicit_local_model_path(monkeypatch, tmp_path: Path) -> None:
    calls, _fake_model = _install_fake_qwen_runtime(monkeypatch, cuda=False)
    model_path = tmp_path / "qwen-model"
    model_path.mkdir()
    monkeypatch.setenv("JAPANMFA_ASR_MODEL_PATH", str(model_path))

    worker._load_model("Qwen/request-model")

    assert calls[0][0] == str(model_path)


def test_load_model_rejects_invalid_explicit_local_model_path(monkeypatch, tmp_path: Path) -> None:
    calls, _fake_model = _install_fake_qwen_runtime(monkeypatch, cuda=False)
    monkeypatch.setenv("JAPANMFA_ASR_MODEL_PATH", str(tmp_path / "missing-model"))

    try:
        worker._load_model("Qwen/request-model")
    except ValueError as exc:
        assert "JAPANMFA_ASR_MODEL_PATH" in str(exc)
    else:  # pragma: no cover - assertion keeps the expected failure explicit
        raise AssertionError("invalid explicit model path must fail")
    assert calls == []


def test_load_model_uses_cpu_when_cuda_is_unavailable_and_not_required(
    monkeypatch,
) -> None:
    calls, _fake_model = _install_fake_qwen_runtime(monkeypatch, cuda=False)
    monkeypatch.delenv("JAPANMFA_REQUIRE_CUDA", raising=False)

    worker._load_model("Qwen/custom")

    assert calls[0][1]["dtype"] == "fp32"
    assert calls[0][1]["device_map"] == "cpu"


def test_load_model_rejects_cpu_when_cuda_is_explicitly_required(monkeypatch) -> None:
    calls, _fake_model = _install_fake_qwen_runtime(monkeypatch, cuda=False)
    monkeypatch.setenv("JAPANMFA_REQUIRE_CUDA", "1")

    try:
        worker._load_model("Qwen/custom")
    except RuntimeError as exc:
        assert "CUDA" in str(exc)
    else:  # pragma: no cover - assertion keeps the expected failure explicit
        raise AssertionError("explicit CUDA requirement must fail without CUDA")
    assert calls == []
