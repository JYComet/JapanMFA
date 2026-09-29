"""JSON subprocess worker that owns the Qwen3-ASR and ForcedAligner runtime."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .checkpoint import DEFAULT_ALIGNER_MODEL, local_native_aligner_dir as _local_native_aligner_dir, native_aligner_checkpoint_state
from .timestamps import clean_asr_text, project_timestamps


_TRUE_ENV_VALUES = frozenset({"1", "true", "yes"})


def _cuda_required() -> bool:
    return os.environ.get("JAPANMFA_REQUIRE_CUDA", "0").casefold() in _TRUE_ENV_VALUES


def _model_source(model_name: str, env_name: str = "JAPANMFA_ASR_MODEL_PATH") -> str:
    configured = os.environ.get(env_name)
    if not configured:
        if env_name == "JAPANMFA_ALIGNER_MODEL_PATH" and model_name == DEFAULT_ALIGNER_MODEL:
            local = _local_native_aligner_dir()
            if native_aligner_checkpoint_state(local) == "ok":
                return str(local)
        return model_name
    path = Path(configured).expanduser()
    if not path.is_dir():
        raise ValueError(f"{env_name} must point to an existing model directory")
    return str(path)


def _device_kwargs() -> dict[str, Any]:
    import torch

    if torch.cuda.is_available():
        return {"dtype": torch.bfloat16, "device_map": "cuda:0"}
    if _cuda_required():
        raise RuntimeError("CUDA is required by JAPANMFA_REQUIRE_CUDA but unavailable")
    return {"dtype": torch.float32, "device_map": "cpu"}


def _load_model(model_name: str) -> Any:
    """Load Qwen only inside the worker process, never in the orchestrator."""
    from qwen_asr import Qwen3ASRModel

    return Qwen3ASRModel.from_pretrained(
        _model_source(model_name),
        **_device_kwargs(),
        local_files_only=True,
        max_inference_batch_size=32,
        max_new_tokens=256,
    )


def _load_aligner(model_name: str) -> Any:
    from qwen_asr import Qwen3ForcedAligner

    return Qwen3ForcedAligner.from_pretrained(
        _model_source(model_name, "JAPANMFA_ALIGNER_MODEL_PATH"),
        **_device_kwargs(),
        local_files_only=True,
    )


def _field(result: Any, name: str) -> Any:
    if isinstance(result, Mapping):
        return result.get(name)
    return getattr(result, name, None)


def _validate_request(request: dict[str, Any]) -> tuple[str, str | None, list[str], list[str | None]]:
    model_name = request.get("model")
    aligner_model = request.get("aligner_model")
    language = request.get("language")
    audio_paths = request.get("audio_paths")
    if not isinstance(model_name, str) or not model_name:
        raise ValueError("request model must be a non-empty string")
    if aligner_model is not None and (not isinstance(aligner_model, str) or not aligner_model):
        raise ValueError("request aligner_model must be a non-empty string")
    if language != "Japanese":
        raise ValueError("request language must be Japanese")
    if not isinstance(audio_paths, list) or not all(
        isinstance(path, str) and path and Path(path).is_absolute() for path in audio_paths
    ):
        raise ValueError("request audio_paths must contain absolute path strings")
    if len(set(audio_paths)) != len(audio_paths):
        raise ValueError("request audio_paths must not contain duplicates")
    references = request.get("reference_texts", [None] * len(audio_paths))
    if not isinstance(references, list) or len(references) != len(audio_paths) or not all(
        value is None or isinstance(value, str) for value in references
    ):
        raise ValueError("request reference_texts must match audio_paths")
    if aligner_model is None and any(value is not None for value in references):
        raise ValueError("reference_texts require aligner_model")
    return model_name, aligner_model, audio_paths, references


def transcribe_request(
    request: dict[str, Any],
    model_factory: Callable[[str], Any] = _load_model,
    aligner_factory: Callable[[str], Any] = _load_aligner,
) -> dict[str, list[dict[str, Any]]]:
    """Run one Japanese request and project punctuation onto lexical gaps."""
    model_name, aligner_model, audio_paths, references = _validate_request(request)
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

    aligner = None
    results: list[dict[str, Any]] = []
    for audio_path, transcription, reference in zip(audio_paths, transcriptions, references):
        language = _field(transcription, "language")
        raw_text = _field(transcription, "text")
        if not isinstance(language, str) or not isinstance(raw_text, str):
            raise ValueError("Qwen3-ASR result language and text must be strings")
        text = clean_asr_text(raw_text)
        if not text:
            raise ValueError("Qwen3-ASR returned no spoken text")
        result: dict[str, Any] = {"audio_path": audio_path, "language": language, "text": text}
        if language == "Japanese" and aligner_model is not None:
            if aligner is None:
                aligner = aligner_factory(aligner_model)
            alignment_text = clean_asr_text(reference) if reference is not None else text
            if not alignment_text:
                raise ValueError("Japanese alignment text has no spoken content")
            aligned = aligner.align(audio=audio_path, text=alignment_text, language="Japanese")
            lexical, punctuation = project_timestamps(alignment_text, aligned)
            result.update({
                "aligner_model": aligner_model,
                "alignment_text": alignment_text,
                "lexical_timestamps": lexical,
                "punctuation_timestamps": punctuation,
            })
        results.append(result)
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
