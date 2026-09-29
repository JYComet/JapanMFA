"""Batch export of normalized Japanese audio and timed ASR words."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from japanmfa.asr.qwen3 import ASRResult, Qwen3ASRClient
from japanmfa.asr.word_kana import merge_timed_words
from japanmfa.audio import AudioInfo, AudioNormalizer
from japanmfa.config import PipelineConfig
from japanmfa.corpus import discover_utterances
from japanmfa.domain import SourceText, Utterance
from japanmfa.errors import SkipUtterance, StageFailure
from japanmfa.frontend.japanese import JapaneseFrontend, render_locked_kana
from japanmfa.frontend.overrides import (
    ReadingOverrideSet,
    apply_reading_overrides,
    load_reading_overrides,
)
from japanmfa.output.reports import write_json


@dataclass(frozen=True)
class ASRBatchResult:
    manifest_path: Path
    summary_path: Path
    summary: dict[str, Any]


def _atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _item_directory(root: Path, utterance_id: str) -> Path:
    relative = Path(utterance_id)
    if relative.is_absolute() or not relative.parts or any(part in {".", ".."} for part in relative.parts):
        raise ValueError(f"unsafe utterance ID: {utterance_id}")
    destination = root / relative
    if root not in destination.parents:
        raise ValueError(f"unsafe utterance ID: {utterance_id}")
    return destination


def _error_row(utterance: Utterance, exc: Exception) -> dict[str, str]:
    if isinstance(exc, SkipUtterance):
        status, reason, stage = "skipped", exc.reason_code, "asr"
    elif isinstance(exc, StageFailure):
        status = "skipped" if exc.reason_code in {"non_japanese_language", "unsupported_japanese_text"} else "failed"
        reason, stage = exc.reason_code, exc.stage
    else:
        status, reason, stage = "failed", "unexpected_exception", "asr_batch"
    return {
        "utterance_id": utterance.utterance_id,
        "status": status,
        "stage": stage,
        "reason_code": reason,
        "message": str(exc),
    }


class ASRBatchRunner:
    """Normalize one corpus, batch Qwen inference, and export reusable WAV/TXT pairs."""

    def __init__(
        self,
        config: PipelineConfig,
        *,
        audio_normalizer: AudioNormalizer | None = None,
        asr_client: Qwen3ASRClient | None = None,
        frontend: JapaneseFrontend | None = None,
    ) -> None:
        self.config = config
        self.audio_normalizer = audio_normalizer or AudioNormalizer(config)
        self.asr_client = asr_client or Qwen3ASRClient(
            config.commands.asr_worker, config.asr.model, config.asr.aligner_model
        )
        self.frontend = frontend or JapaneseFrontend()

    def _transcribe(
        self, paths: list[Path]
    ) -> tuple[dict[Path, ASRResult], dict[Path, Exception]]:
        if not paths:
            return {}, {}
        try:
            return self.asr_client.transcribe(paths), {}
        except (StageFailure, SkipUtterance) as exc:
            if len(paths) == 1:
                return {}, {paths[0]: exc}
            middle = len(paths) // 2
            left, left_errors = self._transcribe(paths[:middle])
            right, right_errors = self._transcribe(paths[middle:])
            return {**left, **right}, {**left_errors, **right_errors}

    def _publish_item(
        self,
        utterance: Utterance,
        audio: AudioInfo,
        result: ASRResult,
        overrides: ReadingOverrideSet,
        artifact: Path,
    ) -> None:
        if result.audio_path != audio.working_path:
            raise StageFailure("asr", "result_coverage_mismatch", "ASR audio path differs from normalized WAV")
        if result.language != "Japanese":
            raise SkipUtterance("non_japanese_language", "ASR result is not Japanese")
        if result.alignment_text != result.text or not result.lexical_timestamps:
            raise StageFailure("asr", "timestamp_unavailable", "ASR text lacks matching Qwen lexical timestamps")
        text = result.text
        source = SourceText(original=text, processing=text, source="asr")
        tokens = self.frontend.analyze(source)
        tokens = apply_reading_overrides(utterance.utterance_id, text, tokens, overrides)
        words = merge_timed_words(text, result.lexical_timestamps, tokens)
        kana = render_locked_kana(text, tokens)
        stem = Path(utterance.utterance_id).name
        receipt = {
            "schema": "japanmfa-asr-batch-v1",
            "audio_file": f"{stem}.wav",
            "text_file": f"{stem}.txt",
            "model": result.model,
            "aligner_model": result.aligner_model,
            "language": result.language,
            "text": text,
            "kana": kana,
            "words": words,
            "punctuation": [vars(item) for item in result.punctuation_timestamps],
            "sample_rate": audio.working_sample_rate,
            "frames": audio.working_frames,
        }
        _atomic_bytes(artifact / f"{stem}.txt", (text + "\n").encode("utf-8"))
        write_json(artifact / f"{stem}.json", receipt)

    def run(
        self,
        input_root: Path,
        output_root: Path,
        *,
        limit: int | None = None,
        overrides_path: Path | None = None,
    ) -> ASRBatchResult:
        source = Path(input_root).resolve(strict=True)
        destination_input = Path(output_root)
        if not source.is_dir() or destination_input.is_symlink():
            raise ValueError("input must be a directory and output must not be a symlink")
        destination = destination_input.resolve(strict=False)
        if source == destination or source in destination.parents or destination in source.parents:
            raise ValueError("input and output roots must be disjoint")
        if limit is not None and limit <= 0:
            raise ValueError("limit must be a positive integer")
        if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
            raise ValueError("ASR batch output must be a new or empty directory")
        utterances = discover_utterances(source)
        if limit is not None:
            utterances = utterances[:limit]
        overrides = load_reading_overrides(overrides_path) if overrides_path else ReadingOverrideSet({})
        destination.mkdir(parents=True, exist_ok=True)

        prepared: dict[Path, tuple[Utterance, AudioInfo, Path]] = {}
        errors: dict[str, Exception] = {}
        for utterance in utterances:
            artifact = _item_directory(destination, utterance.utterance_id)
            stem = Path(utterance.utterance_id).name
            try:
                info = self.audio_normalizer.prepare(utterance.audio_path, artifact / f"{stem}.wav")
                prepared[info.working_path] = utterance, info, artifact
            except Exception as exc:
                errors[utterance.utterance_id] = exc
                if artifact.exists():
                    shutil.rmtree(artifact)

        transcriptions, asr_errors = self._transcribe(list(prepared))
        rows: list[dict[str, str]] = []
        for utterance in utterances:
            early_error = errors.get(utterance.utterance_id)
            if early_error is not None:
                rows.append(_error_row(utterance, early_error))
                continue
            stem = Path(utterance.utterance_id).name
            artifact = _item_directory(destination, utterance.utterance_id)
            audio_path = artifact / f"{stem}.wav"
            _, info, _ = prepared[audio_path]
            try:
                if audio_path in asr_errors:
                    raise asr_errors[audio_path]
                result = transcriptions.get(audio_path)
                if result is None:
                    raise StageFailure("asr", "result_coverage_mismatch", "ASR omitted one normalized WAV")
                self._publish_item(utterance, info, result, overrides, artifact)
                rows.append({"utterance_id": utterance.utterance_id, "status": "transcribed"})
            except Exception as exc:
                rows.append(_error_row(utterance, exc))
                if artifact.exists():
                    shutil.rmtree(artifact)

        counts = {status: sum(row["status"] == status for row in rows)
                  for status in ("transcribed", "skipped", "failed")}
        summary: dict[str, Any] = {"input_count": len(utterances), "counts": counts}
        manifest_path = destination / "manifest.jsonl"
        summary_path = destination / "summary.json"
        _atomic_bytes(manifest_path, "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
        ).encode("utf-8"))
        write_json(summary_path, summary)
        return ASRBatchResult(manifest_path, summary_path, summary)
