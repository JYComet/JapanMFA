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


def test_load_model_uses_qwen_runtime_seam_without_forced_aligner(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class FakeQwenModel:
        @classmethod
        def from_pretrained(cls, model_name: str, **kwargs: object) -> object:
            calls.append((model_name, kwargs))
            return cls()

    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(bfloat16="bf16"))
    monkeypatch.setitem(
        sys.modules,
        "qwen_asr",
        types.SimpleNamespace(Qwen3ASRModel=FakeQwenModel),
    )

    model = worker._load_model("Qwen/custom")

    assert isinstance(model, FakeQwenModel)
    assert calls == [
        (
            "Qwen/custom",
            {
                "dtype": "bf16",
                "device_map": "cuda:0",
                "max_inference_batch_size": 32,
                "max_new_tokens": 256,
            },
        )
    ]
