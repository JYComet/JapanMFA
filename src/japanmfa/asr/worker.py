"""JSON subprocess worker that owns the Qwen3-ASR runtime dependency."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any


_TRUE_ENV_VALUES = frozenset({"1", "true", "yes"})


def _cuda_required() -> bool:
    return os.environ.get("JAPANMFA_REQUIRE_CUDA", "0").casefold() in _TRUE_ENV_VALUES


def _model_source(model_name: str) -> str:
    configured = os.environ.get("JAPANMFA_ASR_MODEL_PATH")
    if not configured:
        return model_name
    path = Path(configured).expanduser()
    if not path.is_dir():
        raise ValueError("JAPANMFA_ASR_MODEL_PATH must point to an existing model directory")
    return str(path)


def _load_model(model_name: str) -> Any:
    """Load Qwen only inside the worker process, never in the orchestrator."""
    model_source = _model_source(model_name)
    import torch
    from qwen_asr import Qwen3ASRModel

    if torch.cuda.is_available():
        dtype = torch.bfloat16
        device_map = "cuda:0"
    else:
        if _cuda_required():
            raise RuntimeError("CUDA is required by JAPANMFA_REQUIRE_CUDA but unavailable")
        dtype = torch.float32
        device_map = "cpu"
    return Qwen3ASRModel.from_pretrained(
        model_source,
        dtype=dtype,
        device_map=device_map,
        local_files_only=True,
        max_inference_batch_size=32,
        max_new_tokens=256,
    )


def _field(result: Any, name: str) -> Any:
    if isinstance(result, Mapping):
        return result.get(name)
    return getattr(result, name, None)


def _validate_request(request: dict[str, Any]) -> tuple[str, list[str]]:
    model_name = request.get("model")
    language = request.get("language")
    audio_paths = request.get("audio_paths")
    if not isinstance(model_name, str) or not model_name:
        raise ValueError("request model must be a non-empty string")
    if language != "Japanese":
        raise ValueError("request language must be Japanese")
    if not isinstance(audio_paths, list) or not all(
        isinstance(path, str) and path and Path(path).is_absolute() for path in audio_paths
    ):
        raise ValueError("request audio_paths must contain absolute path strings")
    if len(set(audio_paths)) != len(audio_paths):
        raise ValueError("request audio_paths must not contain duplicates")
    return model_name, audio_paths


def transcribe_request(
    request: dict[str, Any], model_factory: Callable[[str], Any] = _load_model
) -> dict[str, list[dict[str, str]]]:
    """Run one validated request and convert Qwen records to protocol JSON."""
    model_name, audio_paths = _validate_request(request)
    if not audio_paths:
        return {"results": []}

    model = model_factory(model_name)
    transcriptions = model.transcribe(
        audio=audio_paths,
        language=["Japanese"] * len(audio_paths),
        return_time_stamps=False,
    )
    if not isinstance(transcriptions, Sequence) or isinstance(transcriptions, (str, bytes)):
        raise ValueError("Qwen3-ASR response must be a sequence")
    if len(transcriptions) != len(audio_paths):
        raise ValueError("Qwen3-ASR response count does not match request")

    results: list[dict[str, str]] = []
    for audio_path, transcription in zip(audio_paths, transcriptions):
        language = _field(transcription, "language")
        text = _field(transcription, "text")
        if not isinstance(language, str) or not isinstance(text, str):
            raise ValueError("Qwen3-ASR result language and text must be strings")
        results.append({"audio_path": audio_path, "language": language, "text": text})
    return {"results": results}


def main() -> int:
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("request must be a JSON object")
        response = transcribe_request(request)
    except Exception as exc:  # pragma: no cover - exercised through client exit handling
        print(f"ASR worker failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(response, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
