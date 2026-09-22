"""Japanese-locked client for the isolated Qwen3-ASR worker."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from japanmfa.errors import StageFailure


@dataclass(frozen=True)
class ASRResult:
    """A transcription returned for one absolute working-audio path."""

    audio_path: Path
    language: str
    text: str
    model: str


class Qwen3ASRClient:
    """Invoke Qwen3-ASR through its one-request/one-response subprocess API."""

    def __init__(self, command: Sequence[str], model: str = "Qwen/Qwen3-ASR-1.7B") -> None:
        if not command or not all(isinstance(part, str) and part for part in command):
            raise ValueError("command must be a non-empty argument array")
        if not model:
            raise ValueError("model must be a non-empty string")
        self._command = tuple(command)
        self._model = model

    def transcribe(self, audio_paths: Sequence[Path]) -> dict[Path, ASRResult]:
        """Transcribe absolute paths and validate the complete worker response."""
        requested = list(audio_paths)
        paths: list[Path] = []
        for audio_path in requested:
            path = Path(audio_path)
            if not path.is_absolute():
                raise StageFailure(
                    "asr",
                    "audio_path_not_absolute",
                    f"ASR audio path must be absolute: {path}",
                    {"audio_path": str(path)},
                )
            paths.append(path)

        if len(set(paths)) != len(paths):
            raise StageFailure(
                "asr",
                "duplicate_audio_path",
                "ASR request contains duplicate audio paths",
                {"audio_paths": [str(path) for path in paths]},
            )

        if not paths:
            return {}

        request = {
            "model": self._model,
            "language": "Japanese",
            "audio_paths": [str(path) for path in paths],
        }
        try:
            completed = subprocess.run(
                self._command,
                input=json.dumps(request, ensure_ascii=False),
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            raise StageFailure(
                "asr",
                "worker_start_failed",
                f"could not start ASR worker: {exc}",
                {"command": list(self._command)},
            ) from exc

        if completed.returncode != 0:
            raise StageFailure(
                "asr",
                "worker_failed",
                f"ASR worker exited with status {completed.returncode}",
                {
                    "returncode": completed.returncode,
                    "stderr": completed.stderr[-4000:],
                },
            )

        response = self._parse_response(completed.stdout)
        return self._convert_response(response, paths)

    @staticmethod
    def _parse_response(stdout: str) -> Mapping[str, Any]:
        try:
            response = json.loads(stdout)
        except (json.JSONDecodeError, TypeError) as exc:
            raise StageFailure(
                "asr",
                "malformed_response",
                "ASR worker stdout is not one JSON response",
                {},
            ) from exc
        if not isinstance(response, dict):
            raise StageFailure(
                "asr",
                "malformed_response",
                "ASR worker response must be a JSON object",
                {},
            )
        return response

    def _convert_response(
        self, response: Mapping[str, Any], requested_paths: Sequence[Path]
    ) -> dict[Path, ASRResult]:
        raw_results = response.get("results")
        if not isinstance(raw_results, list):
            raise StageFailure(
                "asr",
                "invalid_response",
                "ASR worker response must contain a results array",
                {},
            )

        converted: dict[Path, ASRResult] = {}
        for raw_result in raw_results:
            if not isinstance(raw_result, dict):
                raise StageFailure(
                    "asr",
                    "invalid_response",
                    "ASR result must be an object",
                    {},
                )
            audio_path = raw_result.get("audio_path")
            language = raw_result.get("language")
            text = raw_result.get("text")
            if not isinstance(audio_path, str) or not audio_path:
                raise StageFailure(
                    "asr",
                    "invalid_response",
                    "ASR result audio_path must be a non-empty string",
                    {},
                )
            result_path = Path(audio_path)
            if not result_path.is_absolute():
                raise StageFailure(
                    "asr",
                    "invalid_response",
                    "ASR result audio_path must be absolute",
                    {"audio_path": audio_path},
                )
            if language != "Japanese":
                raise StageFailure(
                    "asr",
                    "non_japanese_language",
                    f"ASR worker reported unsupported language: {language!r}",
                    {"audio_path": audio_path, "language": language},
                )
            if not isinstance(text, str):
                raise StageFailure(
                    "asr",
                    "invalid_response",
                    "ASR result text must be a string",
                    {"audio_path": audio_path},
                )
            if result_path in converted:
                raise StageFailure(
                    "asr",
                    "result_coverage_mismatch",
                    f"ASR worker returned duplicate result path: {audio_path}",
                    {"audio_path": audio_path},
                )
            converted[result_path] = ASRResult(
                audio_path=result_path,
                language=language,
                text=text,
                model=self._model,
            )

        requested_set = set(requested_paths)
        result_set = set(converted)
        if result_set != requested_set or len(converted) != len(requested_paths):
            missing = sorted(str(path) for path in requested_set - result_set)
            unexpected = sorted(str(path) for path in result_set - requested_set)
            raise StageFailure(
                "asr",
                "result_coverage_mismatch",
                "ASR worker results must cover each requested path exactly once",
                {"missing": missing, "unexpected": unexpected},
            )

        return {path: converted[path] for path in requested_paths}
