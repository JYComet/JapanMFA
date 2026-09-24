"""Japanese-only stage orchestration and per-utterance outcome isolation."""

from __future__ import annotations

import shutil
import stat
import json
import hashlib
import importlib.metadata
import os
import platform
import sys
import tempfile
import time
import traceback
import unicodedata
import wave
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .accent.parser import parse_accent
from .accent.tdmelodic import AccentRequest, TdmelodicClient, resolve_tdmelodic_command
from .asr.qwen3 import ASRResult, Qwen3ASRClient
from .audio import AudioInfo, AudioNormalizer
from .cache import StageCache, stage_fingerprint
from .config import PipelineConfig
from .corpus import discover_utterances, load_source_text
from .domain import (
    Mora,
    PhoneAnnotation,
    Pronunciation,
    SourceText,
    Token,
    Utterance,
    UtteranceOutcome,
)
from .errors import SkipUtterance, StageFailure
from .frontend.japanese import JapaneseFrontend, render_locked_kana
from .frontend.mora import segment_morae
from .frontend.overrides import (
    ReadingOverrideSet,
    apply_reading_overrides,
    load_reading_overrides,
)
from .mfa.g2p import MfaG2pClient
from .mfa.lexicon import LockedLexicon
from .mfa.phone_map import PhoneMap
from .mfa.runner import MfaRunner
from .mfa.textgrid import MfaAlignment, parse_mfa_textgrid
from .output.reports import (
    _redact_string,
    append_manifest,
    redact_command,
    summarize,
    write_json,
    write_yaml,
)
from .output.textgrid import build_word_intervals, validate_five_tier_textgrid, write_five_tier_textgrid
from .projection import project_annotations
from .postprocess import PostprocessResult, annotation_rows, postprocess_annotations


@dataclass(frozen=True)
class BatchResult:
    outcomes: tuple[UtteranceOutcome, ...]
    manifest_path: Path
    summary_path: Path
    output_root: Path
    summary: Mapping[str, object]


def _source_from_asr(text: str) -> SourceText:
    processing = unicodedata.normalize(
        "NFC", text.replace("\r\n", "").replace("\n", "").replace("\r", "").strip()
    )
    return SourceText(original=text, processing=processing, source="asr")


def _duration(audio: AudioInfo, alignment: MfaAlignment) -> float:
    if audio.working_frames > 0 and audio.working_sample_rate > 0:
        return audio.working_frames / audio.working_sample_rate
    if audio.duration > 0:
        return audio.duration
    positive_ends = [phone.end for phone in alignment.phones]
    if positive_ends:
        return max(positive_ends)
    raise StageFailure("audio", "duration_unavailable", "audio duration is not positive")


def _valid_audio_artifact(path: Path) -> bool:
    try:
        metadata = path.stat()
    except OSError:
        return False
    return not path.is_symlink() and stat.S_ISREG(metadata.st_mode) and metadata.st_size > 0


def _valid_working_audio(path: Path, sample_rate: int) -> bool:
    if not _valid_audio_artifact(path):
        return False
    try:
        with wave.open(str(path), "rb") as stream:
            return (stream.getnchannels() == 1 and stream.getsampwidth() == 2
                    and stream.getframerate() == sample_rate and stream.getnframes() > 0)
    except (EOFError, OSError, wave.Error):
        return False


def _reject_symlink_components(path: Path) -> None:
    """Reject symlinks in a path before any caller creates or writes below it."""
    absolute = Path(path).absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            break
        except OSError as exc:
            raise ValueError(f"could not inspect output path: {current}: {exc}") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f"output path cannot contain symlink components: {current}")


def _paths_overlap(first: Path, second: Path) -> bool:
    """Return whether either resolved path contains the other."""
    return first == second or first in second.parents or second in first.parents


def _safe_output_path(root: Path, relative: str | Path) -> Path:
    """Return a path proven to remain below the project-owned output root."""
    trusted_root = Path(root).absolute()
    relative_path = Path(relative)
    if relative_path.is_absolute() or any(part in {"", ".", ".."} for part in relative_path.parts):
        raise ValueError(f"output relative path is invalid: {relative_path}")
    candidate = trusted_root.joinpath(relative_path)
    _reject_symlink_components(candidate)
    try:
        resolved_root = trusted_root.resolve(strict=True)
        resolved_candidate = candidate.resolve(strict=False)
    except OSError as exc:
        raise ValueError(f"could not resolve output path: {candidate}: {exc}") from exc
    if resolved_candidate != resolved_root and resolved_root not in resolved_candidate.parents:
        raise ValueError(f"output path escapes trusted output root: {candidate}")
    return candidate


def _ensure_output_directory(root: Path, relative: str | Path = ".") -> Path:
    directory = Path(root).absolute() if str(relative) == "." else _safe_output_path(root, relative)
    _reject_symlink_components(directory)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ValueError(f"could not create output directory: {directory}: {exc}") from exc
    _reject_symlink_components(directory)
    if not directory.is_dir():
        raise ValueError(f"output path is not a directory: {directory}")
    resolved_root = Path(root).absolute().resolve(strict=True)
    resolved_directory = directory.resolve(strict=True)
    if resolved_directory != resolved_root and resolved_root not in resolved_directory.parents:
        raise ValueError(f"output directory escapes trusted output root: {directory}")
    return directory


def _unlink_published(path: Path) -> None:
    """Remove one published output without ever following a symlink."""
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISLNK(metadata.st_mode) or stat.S_ISREG(metadata.st_mode):
        path.unlink()
        return
    raise OSError(f"published output is not a regular file: {path}")


def _cleanup_published_outputs(paths: tuple[Path, ...]) -> None:
    """Remove every published final, reporting the first cleanup failure."""
    first_error: OSError | None = None
    for path in paths:
        try:
            _unlink_published(path)
        except OSError as exc:
            if first_error is None:
                first_error = exc
    if first_error is not None:
        raise first_error


def _published_cleanup_error(paths: tuple[Path, ...]) -> str | None:
    """Best-effort cleanup for exception paths while preserving batch isolation."""
    try:
        _cleanup_published_outputs(paths)
    except OSError as exc:
        return str(exc)
    return None


def _publish_final_outputs(
    artifact_dir: Path,
    final_grid: Path,
    final_alignment: Path,
    duration: float,
    source: str,
    kana: str,
    annotations: tuple[PhoneAnnotation, ...],
    silence_labels: frozenset[str],
    words: tuple[tuple[float, float, str], ...],
    working_audio: Path,
    audio_receipt: Mapping[str, object],
) -> None:
    """Validate both final artifacts in a private dir, then publish with a marker."""
    complete_marker = artifact_dir / ".japanmfa.complete"
    final_audio = artifact_dir / f"{final_grid.stem}.wav"
    final_audio_json = artifact_dir / "audio.json"
    published = (final_grid, final_alignment, final_audio, final_audio_json, complete_marker)
    for path in published:
        _reject_symlink_components(path)
    _cleanup_published_outputs(published)

    staging = Path(tempfile.mkdtemp(prefix=".publish-", dir=artifact_dir))
    staged_grid = staging / final_grid.name
    staged_alignment = staging / final_alignment.name
    staged_audio = staging / final_audio.name
    staged_audio_json = staging / final_audio_json.name
    staged_marker = staging / complete_marker.name
    try:
        write_five_tier_textgrid(staged_grid, duration, source, kana, annotations, words=words)
        validate_five_tier_textgrid(staged_grid, duration, silence_labels)
        write_json(
            staged_alignment,
            {
                "textgrid": str(final_grid),
                "duration": duration,
                "phones": annotation_rows(annotations),
                "words": [{"start": start, "end": end, "label": label} for start, end, label in words],
                "tone_encoding": "HH_LL_HL_LH",
                "tone_source": "tdmelodic_predicted_mora_accent_not_measured_f0",
                "audio": str(final_audio),
                "audio_receipt": str(final_audio_json),
                "audio_sha256": audio_receipt.get("working_sha256"),
                "audio_frames": audio_receipt.get("working_frames"),
                "audio_sample_rate": audio_receipt.get("working_sample_rate"),
            },
        )
        receipt = dict(audio_receipt)
        required_receipt = ("working_sample_rate", "working_frames", "working_sha256")
        if any(key not in receipt for key in required_receipt):
            raise OSError("audio receipt is incomplete")
        shutil.copy2(working_audio, staged_audio)
        write_json(staged_audio_json, receipt)
        with wave.open(str(staged_audio), "rb") as audio_stream:
            if (audio_stream.getnchannels() != 1 or audio_stream.getsampwidth() != 2
                    or audio_stream.getframerate() != int(receipt["working_sample_rate"])
                    or audio_stream.getnframes() != int(receipt["working_frames"])
                    or abs(audio_stream.getnframes() / audio_stream.getframerate() - duration)
                    > (1.0 / audio_stream.getframerate() + 1e-6)):
                raise OSError("published WAV header does not match audio receipt or duration")
        if hashlib.sha256(staged_audio.read_bytes()).hexdigest() != receipt["working_sha256"]:
            raise OSError("published WAV hash does not match audio receipt")
        required = [staged_grid, staged_alignment]
        required.extend([staged_audio, staged_audio_json])
        if not all(_valid_audio_artifact(path) for path in required):
            raise OSError("staged final output is missing or not a regular non-empty file")
        try:
            json.loads(staged_alignment.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise OSError("staged alignment.json is not valid JSON") from exc

        os.replace(staged_grid, final_grid)
        os.replace(staged_alignment, final_alignment)
        os.replace(staged_audio, final_audio)
        os.replace(staged_audio_json, final_audio_json)
        write_json(
            staged_marker,
            {
                "textgrid": str(final_grid),
                "alignment": str(final_alignment),
                "audio": str(final_audio),
                "audio_receipt": str(final_audio_json),
                "duration": duration,
                "working_sha256": receipt["working_sha256"],
                "working_frames": receipt["working_frames"],
            },
        )
        if not _valid_audio_artifact(staged_marker):
            raise OSError("staged completion marker is missing")
        os.replace(staged_marker, complete_marker)
    except BaseException:
        cleanup_error = _published_cleanup_error(published)
        if cleanup_error is not None:
            raise OSError(
                f"failed to remove partial final outputs: {cleanup_error}"
            )
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _token_payload(tokens: tuple[Token, ...]) -> list[dict[str, object]]:
    return [
        {
            "index": token.index,
            "start": token.start,
            "end": token.end,
            "surface": token.surface,
            "part_of_speech": list(token.part_of_speech),
            "reading": token.reading,
            "reading_source": token.reading_source,
        }
        for token in tokens
    ]


def _mora_payload(morae: Mapping[int, tuple[Mora, ...]]) -> list[dict[str, object]]:
    return [
        {
            "token_index": token_index,
            "morae": [
                {"index_in_token": mora.index_in_token, "kana": mora.kana, "tone": mora.tone}
                for mora in values
            ],
        }
        for token_index, values in sorted(morae.items())
    ]


def _audit_text(value: str) -> str:
    """Normalize text for ASR comparison without changing the source artifact."""
    return unicodedata.normalize("NFKC", value).replace("\r\n", "").replace("\n", "").replace("\r", "").strip()


def _with_sp1(value: str) -> str:
    return value if value.startswith("<sp") else f"<sp1>{value}"


def _punctuation_groups(value: str) -> tuple[str, ...]:
    """Return source punctuation groups without treating Japanese ー as punctuation."""
    groups: list[str] = []
    current: list[str] = []
    for character in value:
        if unicodedata.category(character).startswith("P"):
            current.append(character)
        elif current:
            groups.append("".join(current))
            current = []
    if current:
        groups.append("".join(current))
    return tuple(groups)


def _asr_comparison(source: SourceText, asr_result: ASRResult | None) -> dict[str, object]:
    if source.source != "txt":
        return {"performed": False, "reason": "no_authoritative_text"}
    if asr_result is None:
        return {"performed": False, "reason": "asr_result_unavailable"}
    authoritative = _audit_text(source.original)
    asr_text = _audit_text(asr_result.text)
    equal = authoritative == asr_text
    return {
        "performed": True,
        "normalization": "NFKC; remove CR/LF; trim surrounding whitespace",
        "authoritative_normalized": authoritative,
        "asr_normalized": asr_text,
        "equal": equal,
        "difference": None if equal else {
            "authoritative": authoritative,
            "asr": asr_text,
        },
    }


def _package_versions() -> dict[str, str]:
    packages = (
        ("japanmfa", "japanmfa"),
        ("PyYAML", "PyYAML"),
        ("praatio", "praatio"),
        ("sudachipy", "SudachiPy"),
        ("sudachidict_core", "sudachidict_core"),
        ("typer", "typer"),
    )
    versions: dict[str, str] = {}
    for label, distribution in packages:
        try:
            versions[label] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[label] = "unavailable"
    return versions


def _resolved_config_payload(
    config: PipelineConfig,
    input_root: Path,
    output_root: Path,
    utterance_count: int,
    limit: int | None,
    tdmelodic_command: tuple[str, ...],
) -> dict[str, object]:
    asr_model_path = os.environ.get("JAPANMFA_ASR_MODEL_PATH")
    require_cuda_raw = os.environ.get("JAPANMFA_REQUIRE_CUDA", "0")
    require_cuda = require_cuda_raw.casefold() in {"1", "true", "yes"}
    return {
        "japanmfa": {
            "version": __import__("japanmfa").__version__,
            "python": platform.python_version(),
            "python_executable": sys.executable,
        },
        "dependencies": _package_versions(),
        "config": {
            "asr": {
                "model": config.asr.model,
                "fallback_model": config.asr.fallback_model,
                "language": config.asr.language,
            },
            "mfa": {
                "acoustic_model": config.mfa.acoustic_model,
                "g2p_model": config.mfa.g2p_model,
                "dither": config.mfa.dither,
            },
            "audio": {
                "sample_rate": config.audio.sample_rate,
                "max_silence_sec": config.audio.max_silence_sec,
                "sil_vol_threshold": config.audio.sil_vol_threshold,
                "sil_len_threshold": config.audio.sil_len_threshold,
                "normalize_edges": config.audio.normalize_edges,
                "target_edge_silence_sec": config.audio.target_edge_silence_sec,
                "edge_silence_threshold": config.audio.edge_silence_threshold,
                "edge_frame_length": config.audio.edge_frame_length,
            },
            "commands": {
                "ffmpeg": redact_command(config.commands.ffmpeg),
                "asr_worker": redact_command(config.commands.asr_worker),
                "mfa": redact_command(config.commands.mfa),
                "tdmelodic": redact_command(tdmelodic_command),
            },
            "paths": {
                "cache_dir": str(Path(config.paths.cache_dir).resolve()),
                "output_dir": str(output_root),
            },
            "validation": {
                "silence_labels": list(config.validation.silence_labels),
                "enable_word_in_silence_filter": config.validation.enable_word_in_silence_filter,
            },
        },
        "models": {
            "asr": {
                "configured_id": config.asr.model,
                "model_path": asr_model_path,
            },
            "asr_fallback": {"configured_id": config.asr.fallback_model},
            "mfa_acoustic": config.mfa.acoustic_model,
            "mfa_g2p": config.mfa.g2p_model,
        },
        "device_policy": {
            "require_cuda": require_cuda,
            "configured_value": require_cuda_raw,
            "selection": "cuda_required" if require_cuda else "cuda_if_available_else_cpu",
        },
        "commands": {
            "ffmpeg": redact_command(config.commands.ffmpeg),
            "asr_worker": redact_command(config.commands.asr_worker),
            "mfa": redact_command(config.commands.mfa),
            "tdmelodic": redact_command(tdmelodic_command),
        },
        "paths": {
            "input_root": str(input_root),
            "output_root": str(output_root),
            "cache_dir": str(Path(config.paths.cache_dir).resolve()),
        },
        "batch": {"utterance_count": utterance_count, "limit": limit},
    }


def _adapter_id(adapter: object) -> str:
    def environment_identity(value: Mapping[object, object]) -> dict[str, object]:
        if any(not isinstance(key, str) for key in value):
            raise TypeError("string mapping keys are required for adapter identity")
        hashed: dict[str, object] = {}
        for key, raw in sorted(value.items()):
            rendered = str(raw)
            if os.environ.get(key) == rendered:
                continue
            digest = hashlib.sha256(f"{key}\0{rendered}".encode("utf-8")).hexdigest()
            hashed[key] = {"sha256": digest}
        return {"values": hashed}

    def stable(value: object) -> object:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, Mapping):
            if any(not isinstance(key, str) for key in value):
                raise TypeError("string mapping keys are required for adapter identity")
            return {str(key): stable(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
        if isinstance(value, (tuple, list)):
            return [stable(item) for item in value]
        if isinstance(value, (set, frozenset)):
            entries = [stable(item) for item in value]
            entries.sort(key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            return {"__type__": "set" if isinstance(value, set) else "frozenset", "items": entries}
        if hasattr(value, "__dict__"):
            return stable(vars(value))
        return f"{type(value).__module__}.{type(value).__qualname__}"

    state: dict[str, object] = {}
    for name, value in sorted(getattr(adapter, "__dict__", {}).items()):
        normalized = name.lstrip("_")
        if normalized in {"tokenizer", "runtime_object"} or callable(value):
            continue
        if normalized == "env" and isinstance(value, Mapping):
            state[normalized] = environment_identity(value)
            continue
        state[normalized] = stable(value)
    rendered = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{type(adapter).__module__}.{type(adapter).__qualname__}:{rendered}"


def _tokens_from_payload(payload: list[dict[str, object]]) -> tuple[Token, ...]:
    return tuple(
        Token(
            int(item["index"]),
            int(item["start"]),
            int(item["end"]),
            str(item["surface"]),
            tuple(str(value) for value in item.get("part_of_speech", [])),
            str(item["reading"]),
            str(item["reading_source"]),  # type: ignore[arg-type]
        )
        for item in payload
    )


def _morae_from_payload(payload: list[dict[str, object]]) -> dict[int, tuple[Mora, ...]]:
    result: dict[int, tuple[Mora, ...]] = {}
    for item in payload:
        token_index = int(item["token_index"])
        result[token_index] = tuple(
            Mora(token_index, int(value["index_in_token"]), str(value["kana"]), value.get("tone"))  # type: ignore[arg-type]
            for value in item["morae"]  # type: ignore[union-attr]
        )
    return result


class JapanMFAPipeline:
    """Run all Japanese alignment stages while isolating each utterance."""

    def __init__(
        self,
        config: PipelineConfig | None = None,
        *,
        audio_normalizer: Any | None = None,
        asr_client: Any | None = None,
        frontend: Any | None = None,
        accent_client: Any | None = None,
        g2p_client: Any | None = None,
        mfa_runner: Any | None = None,
        phone_map: PhoneMap | None = None,
        cache: Any | None = None,
    ) -> None:
        self.config = config or PipelineConfig()
        self.audio_normalizer = audio_normalizer
        self.asr_client = asr_client
        self.frontend = frontend
        self.accent_client = accent_client
        self.g2p_client = g2p_client
        self.mfa_runner = mfa_runner
        self.phone_map = phone_map
        self.cache = cache

    def _defaults(self, artifact_dir: Path) -> tuple[Any, ...]:
        audio = self.audio_normalizer or AudioNormalizer(self.config)
        asr = self.asr_client or Qwen3ASRClient(self.config.commands.asr_worker, self.config.asr.model)
        frontend = self.frontend or JapaneseFrontend()
        accent = self.accent_client or TdmelodicClient(resolve_tdmelodic_command())
        g2p = self.g2p_client or MfaG2pClient(self.config.commands.mfa, self.config.mfa.g2p_model)
        phone_map = self.phone_map or PhoneMap.load(
            Path(__file__).parent / "mfa" / "data" / "japanese_mfa_v3_phone_map.yaml"
        )
        mfa = self.mfa_runner
        if mfa is None:
            mfa = MfaRunner(
                self.config.commands.mfa,
                self.config.mfa.acoustic_model,
                owned_root=artifact_dir / "mfa",
                dither=self.config.mfa.dither,
            )
        return audio, asr, frontend, accent, g2p, mfa, phone_map

    def run(
        self,
        input_root: Path,
        output_root: Path,
        overrides: Path | None,
        *,
        limit: int | None = None,
    ) -> BatchResult:
        input_root = Path(input_root).resolve()
        requested_output_root = Path(output_root).absolute()
        _reject_symlink_components(requested_output_root)
        output_root = requested_output_root.resolve(strict=False)
        if _paths_overlap(input_root, output_root):
            raise ValueError("output root must not overlap input root")
        if not input_root.is_dir():
            raise ValueError(f"input root is not a directory: {input_root}")

        configured_cache_root = getattr(
            self.cache, "root", self.config.paths.cache_dir
        )
        requested_cache_root = Path(configured_cache_root).absolute()
        _reject_symlink_components(requested_cache_root)
        cache_root = requested_cache_root.resolve(strict=False)
        if _paths_overlap(input_root, cache_root):
            raise ValueError("cache root must not overlap input root")
        if _paths_overlap(output_root, cache_root):
            raise ValueError("cache root must not overlap output root")

        utterances = discover_utterances(input_root)
        if limit is not None:
            if limit <= 0:
                raise ValueError("limit must be a positive integer")
            utterances = utterances[:limit]
        override_set = ReadingOverrideSet({}) if overrides is None else load_reading_overrides(Path(overrides).resolve())
        cache = self.cache or StageCache(cache_root)
        _ensure_output_directory(output_root)
        for utterance in utterances:
            # Preflight every path before writing resolved config or invoking
            # MFA, including nested speaker/utterance components.
            _safe_output_path(output_root, utterance.utterance_id)
        tdmelodic_command = resolve_tdmelodic_command()
        write_yaml(
            _safe_output_path(output_root, "resolved_config.yaml"),
            _resolved_config_payload(self.config, input_root, output_root, len(utterances), limit, tdmelodic_command),
        )
        manifest_path = _safe_output_path(output_root, "manifest.jsonl")
        if manifest_path.exists():
            manifest_path.unlink()
        outcomes: list[UtteranceOutcome] = []
        for utterance in utterances:
            outcome = self._run_utterance(utterance, output_root, override_set, cache)
            outcomes.append(outcome)
            append_manifest(
                manifest_path,
                outcome,
                source_type="txt" if utterance.text_path is not None else "asr",
            )
        summary = summarize(outcomes)
        summary_path = _safe_output_path(output_root, "summary.json")
        write_json(summary_path, summary)
        return BatchResult(tuple(outcomes), manifest_path, summary_path, output_root, summary)

    def _run_utterance(
        self,
        utterance: Utterance,
        output_root: Path,
        override_set: ReadingOverrideSet,
        cache: StageCache,
    ) -> UtteranceOutcome:
        started = time.monotonic()
        artifact_dir = _ensure_output_directory(output_root, utterance.utterance_id)
        final_grid = _safe_output_path(
            artifact_dir, f"{Path(utterance.audio_path).stem}.TextGrid"
        )
        final_alignment = _safe_output_path(artifact_dir, "alignment.json")
        final_audio = _safe_output_path(artifact_dir, f"{Path(utterance.audio_path).stem}.wav")
        final_audio_json = _safe_output_path(artifact_dir, "audio.json")
        complete_marker = _safe_output_path(artifact_dir, ".japanmfa.complete")
        published_outputs = (final_grid, final_alignment, final_audio, final_audio_json, complete_marker)
        durations: dict[str, float] = {}
        current_stage = "audio"
        cleanup_error = _published_cleanup_error(published_outputs)
        if cleanup_error is not None:
            return UtteranceOutcome(
                utterance.utterance_id,
                "failed",
                "final_cleanup_failed",
                f"could not remove stale final outputs: {cleanup_error}",
                artifact_dir,
                {"output_cleanup": time.monotonic() - started},
            )
        try:
            audio, asr, frontend, accent, g2p, mfa, phone_map = self._defaults(artifact_dir)

            stage_started = time.monotonic()
            audio_fp = stage_fingerprint(
                "audio",
                {"audio": utterance.audio_path, "sample_rate": self.config.audio.sample_rate,
                 "preprocess_revision": "asrmfa-trim-silence-v1",
                 "preprocess": self.config.audio, "adapter": _adapter_id(audio)},
            )

            def produce_audio(path: Path) -> dict[str, object]:
                info = audio.prepare(utterance.audio_path, path / "audio.wav")
                return {
                    "duration": info.duration,
                    "source_sample_rate": info.source_sample_rate,
                    "source_channels": info.source_channels,
                    "working_sample_rate": info.working_sample_rate,
                    "source_frames": info.source_frames,
                    "working_frames": info.working_frames,
                    "source_sha256": info.source_sha256,
                    "working_sha256": info.working_sha256,
                }

            def validate_audio_cache(directory: Path) -> bool:
                artifact = directory / "audio.wav"
                if not _valid_working_audio(artifact, self.config.audio.sample_rate):
                    return False
                # StageCache validates the producer's temporary directory
                # before writing result.json; metadata/hash validation applies
                # to an already published cache entry.
                if not (directory / "result.json").exists():
                    return True
                try:
                    metadata = json.loads((directory / "result.json").read_text(encoding="utf-8"))
                    source_hash = hashlib.sha256(utterance.audio_path.read_bytes()).hexdigest()
                    working_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
                    return (metadata.get("source_sha256") == source_hash
                            and metadata.get("working_sha256") == working_hash)
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    return False

            audio_meta = cache.load_or_run(
                "audio",
                audio_fp,
                produce_audio,
                validate=validate_audio_cache,
            )
            cached_audio = cache.directory("audio", audio_fp) / "audio.wav"
            if not cached_audio.is_file():
                raise StageFailure("audio", "cache_artifact_missing", "cached working audio is missing")
            working_dir = _ensure_output_directory(artifact_dir, "work")
            working_audio = _safe_output_path(working_dir, "audio.wav")
            shutil.copy2(cached_audio, working_audio)
            audio_info = AudioInfo(
                utterance.audio_path,
                working_audio,
                float(audio_meta["duration"]),
                int(audio_meta["source_sample_rate"]),
                int(audio_meta["source_channels"]),
                int(audio_meta["working_sample_rate"]),
                int(audio_meta.get("source_frames", 0)),
                int(audio_meta.get("working_frames", 0)),
                str(audio_meta.get("source_sha256", "")),
                str(audio_meta.get("working_sha256", "")),
            )
            durations["audio"] = time.monotonic() - stage_started

            current_stage = "source"
            stage_started = time.monotonic()
            source_fp = stage_fingerprint(
                "source",
                {
                    "audio": utterance.audio_path,
                    "text": utterance.text_path,
                    "model": self.config.asr.model,
                    "adapter": _adapter_id(asr),
                },
            )

            def produce_source(_path: Path) -> dict[str, object]:
                asr_result: ASRResult | None = None
                if utterance.text_path is not None:
                    source = load_source_text(utterance.text_path)
                    if asr is not None:
                        try:
                            asr_result = asr.transcribe([audio_info.working_path]).get(audio_info.working_path)
                        except StageFailure as exc:
                            if exc.stage == "asr" and exc.reason_code == "non_japanese_language":
                                raise SkipUtterance("non_japanese_language", exc.message, exc.details) from exc
                            raise
                else:
                    if asr is None:
                        raise StageFailure("asr", "unavailable", "ASR is required when .txt is missing")
                    try:
                        asr_result = asr.transcribe([audio_info.working_path]).get(audio_info.working_path)
                    except StageFailure as exc:
                        if exc.stage == "asr" and exc.reason_code == "non_japanese_language":
                            raise SkipUtterance("non_japanese_language", exc.message, exc.details) from exc
                        raise
                    if asr_result is None:
                        raise StageFailure("asr", "result_coverage_mismatch", "ASR returned no result")
                    source = _source_from_asr(asr_result.text)
                if asr_result is not None and asr_result.language != "Japanese":
                    raise SkipUtterance("unsupported_language", "ASR reported a non-Japanese language")
                return {
                    "original": source.original,
                    "processing": source.processing,
                    "source": source.source,
                    "asr": None if asr_result is None else {
                        "model": asr_result.model,
                        "language": asr_result.language,
                        "text": asr_result.text,
                    },
                }

            source_payload = cache.load_or_run("source", source_fp, produce_source)
            source = SourceText(str(source_payload["original"]), str(source_payload["processing"]), str(source_payload["source"]))  # type: ignore[arg-type]
            asr_payload = source_payload.get("asr")
            asr_result = None if asr_payload is None else ASRResult(audio_info.working_path, str(asr_payload["language"]), str(asr_payload["text"]), str(asr_payload["model"]))
            durations["source"] = time.monotonic() - stage_started
            write_json(
                _safe_output_path(artifact_dir, "asr.json"),
                {
                    "model": None if asr_result is None else asr_result.model,
                    "language": None if asr_result is None else asr_result.language,
                    "text": None if asr_result is None else asr_result.text,
                    "source": source.source,
                    "authoritative_text": source.original,
                    "validation": "not_run" if asr_result is None else "language_checked",
                    "comparison": _asr_comparison(source, asr_result),
                },
            )

            current_stage = "frontend"
            stage_started = time.monotonic()
            frontend_fp = stage_fingerprint(
                "frontend",
                {
                    "utterance_id": utterance.utterance_id,
                    "source": source_payload,
                    "overrides": _adapter_id(override_set),
                    "adapter": _adapter_id(frontend),
                },
            )

            def produce_frontend(_path: Path) -> dict[str, object]:
                tokens = frontend.analyze(source)
                tokens = apply_reading_overrides(utterance.utterance_id, source.original, tokens, override_set)
                return {"tokens": _token_payload(tokens), "kana": render_locked_kana(source.original, tokens)}

            frontend_payload = cache.load_or_run("frontend", frontend_fp, produce_frontend)
            tokens = _tokens_from_payload(frontend_payload["tokens"])
            kana = str(frontend_payload["kana"])
            durations["frontend"] = time.monotonic() - stage_started
            write_json(_safe_output_path(artifact_dir, "frontend.json"), {"tokens": _token_payload(tokens), "original": source.original, "kana": kana})

            current_stage = "accent"
            stage_started = time.monotonic()
            accent_fp = stage_fingerprint("accent", {"frontend": frontend_payload, "adapter": _adapter_id(accent)})

            def produce_accent(_path: Path) -> dict[str, object]:
                token_morae = {token.index: segment_morae(token) for token in tokens}
                requests = tuple(AccentRequest(token.index, token.surface, token.reading) for token in tokens)
                marked = accent.predict(requests)
                toned_morae: dict[int, tuple[Mora, ...]] = {}
                for token in tokens:
                    if token.index not in marked:
                        raise StageFailure("accent", "output_coverage_mismatch", "tdmelodic omitted a token", {"token_index": token.index})
                    toned_morae[token.index] = parse_accent(marked[token.index], token_morae[token.index])
                return {"morae": _mora_payload(toned_morae), "tdmelodic": marked}

            accent_payload = cache.load_or_run("accent", accent_fp, produce_accent)
            toned_morae = _morae_from_payload(accent_payload["morae"])
            marked = dict(accent_payload["tdmelodic"])
            durations["accent"] = time.monotonic() - stage_started
            write_json(_safe_output_path(artifact_dir, "mora.json"), {"morae": _mora_payload(toned_morae), "tdmelodic": marked})

            current_stage = "g2p"
            stage_started = time.monotonic()
            g2p_fp = stage_fingerprint("g2p", {"tokens": _token_payload(tokens), "model": self.config.mfa.g2p_model, "adapter": _adapter_id(g2p)})

            def produce_g2p(path: Path) -> dict[str, object]:
                pronunciations = g2p.pronounce(tuple(token.reading for token in tokens), path)
                return {"pronunciations": [{"reading": item.reading, "phones": list(item.phones), "alternates": [list(variant) for variant in item.alternates]} for item in pronunciations]}

            g2p_payload = cache.load_or_run("g2p", g2p_fp, produce_g2p)
            pronunciations = tuple(Pronunciation(str(item["reading"]), tuple(str(phone) for phone in item["phones"]), tuple(tuple(str(phone) for phone in variant) for variant in item.get("alternates", []))) for item in g2p_payload["pronunciations"])
            lexicon = LockedLexicon.build(utterance.utterance_id, tokens, pronunciations)
            mfa_root = _ensure_output_directory(artifact_dir, "mfa")
            corpus_dir = _ensure_output_directory(mfa_root, "corpus")
            dictionary_path = _safe_output_path(mfa_root, "dictionary.dict")
            _safe_output_path(corpus_dir, f"{utterance.utterance_id}.lab")
            _safe_output_path(corpus_dir, "aliases.json")
            lexicon.write(corpus_dir, dictionary_path)
            corpus_audio = _safe_output_path(corpus_dir, f"{utterance.utterance_id}.wav")
            corpus_audio.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(audio_info.working_path, corpus_audio)
            durations["g2p"] = time.monotonic() - stage_started

            current_stage = "mfa"
            stage_started = time.monotonic()
            mfa_output = _safe_output_path(mfa_root, "aligned")
            mfa_work = _safe_output_path(mfa_root, "work")
            _reject_symlink_components(mfa_output)
            _reject_symlink_components(mfa_work)
            raw_grid = mfa.align(corpus_dir, dictionary_path, mfa_output, mfa_work)
            alignment = parse_mfa_textgrid(Path(raw_grid), frozenset(self.config.validation.silence_labels))
            durations["mfa"] = time.monotonic() - stage_started
            write_json(_safe_output_path(artifact_dir, "mfa.json"), {"textgrid": str(raw_grid), "aliases": list(lexicon.aliases), "transcript": lexicon.transcript})

            current_stage = "projection"
            stage_started = time.monotonic()
            annotations = project_annotations(alignment, lexicon, toned_morae, phone_map)
            durations["projection"] = time.monotonic() - stage_started

            current_stage = "postprocess"
            stage_started = time.monotonic()
            duration = _duration(audio_info, alignment)
            processed = postprocess_annotations(
                audio_info.working_path, duration, annotations,
                mfa_alignment=alignment,
                enable_word_in_silence_filter=self.config.validation.enable_word_in_silence_filter,
            )
            write_json(_safe_output_path(artifact_dir, "postprocess.json"), processed.report)
            durations["postprocess"] = time.monotonic() - stage_started
            if not processed.report["passed"]:
                raise StageFailure("postprocess", str(processed.report["reason_code"]),
                                   "acoustic quality checks failed; inspect postprocess.json")
            annotations = processed.annotations

            current_stage = "output"
            stage_started = time.monotonic()
            duration = _duration(audio_info, alignment)
            if _punctuation_groups(source.original) != _punctuation_groups(kana):
                raise StageFailure(
                    "output", "punctuation_source_mismatch",
                    "kana projection changed source punctuation order or grouping",
                )
            words, unplaced_punctuation = build_word_intervals(
                duration, source.original, tokens, alignment.words, lexicon.aliases,
            )
            processed.report["punctuation_unplaced"] = list(unplaced_punctuation)
            write_json(_safe_output_path(artifact_dir, "postprocess.json"), processed.report)
            with wave.open(str(audio_info.working_path), "rb") as _working_stream:
                _working_frames = _working_stream.getnframes()
                _working_rate = _working_stream.getframerate()
            _working_hash = hashlib.sha256(audio_info.working_path.read_bytes()).hexdigest()
            _publish_final_outputs(
                artifact_dir,
                final_grid,
                final_alignment,
                duration,
                _with_sp1(source.original),
                _with_sp1(kana),
                annotations,
                frozenset(self.config.validation.silence_labels),
                words=words,
                working_audio=audio_info.working_path,
                audio_receipt={
                    "source": str(audio_info.source_path),
                    "source_sample_rate": audio_info.source_sample_rate,
                    "source_channels": audio_info.source_channels,
                    "source_duration": audio_info.duration,
                    "source_frames": audio_info.source_frames,
                    "source_sha256": audio_info.source_sha256,
                    "working": str(audio_info.working_path),
                    "working_sample_rate": _working_rate,
                    "working_frames": _working_frames,
                    "working_duration": _working_frames / _working_rate if _working_rate else 0.0,
                    "working_sha256": _working_hash,
                },
            )
            durations["output"] = time.monotonic() - stage_started
            return UtteranceOutcome(utterance.utterance_id, "aligned", None, None, artifact_dir, durations)
        except SkipUtterance as exc:
            cleanup_error = _published_cleanup_error(published_outputs)
            durations[current_stage] = durations.get(current_stage, time.monotonic() - started)
            if cleanup_error is not None:
                return UtteranceOutcome(
                    utterance.utterance_id,
                    "failed",
                    "final_cleanup_failed",
                    f"could not remove final outputs after skip: {cleanup_error}",
                    artifact_dir,
                    durations,
                )
            return UtteranceOutcome(utterance.utterance_id, "skipped", exc.reason_code, exc.message, None, durations)
        except StageFailure as exc:
            cleanup_error = _published_cleanup_error(published_outputs)
            durations[current_stage] = durations.get(current_stage, time.monotonic() - started)
            if cleanup_error is not None:
                return UtteranceOutcome(
                    utterance.utterance_id,
                    "failed",
                    "final_cleanup_failed",
                    f"could not remove final outputs after failure: {cleanup_error}",
                    artifact_dir,
                    durations,
                )
            return UtteranceOutcome(utterance.utterance_id, "failed", exc.reason_code, exc.message, artifact_dir, durations)
        except Exception as exc:  # per-item isolation boundary
            cleanup_error = _published_cleanup_error(published_outputs)
            durations[current_stage] = durations.get(current_stage, time.monotonic() - started)
            trace_path = _safe_output_path(artifact_dir, "traceback.txt")
            trace_path.write_text(_redact_string(traceback.format_exc()), encoding="utf-8")
            if cleanup_error is not None:
                return UtteranceOutcome(
                    utterance.utterance_id,
                    "failed",
                    "final_cleanup_failed",
                    f"could not remove final outputs after exception: {cleanup_error}",
                    artifact_dir,
                    {**durations, "traceback": 0.0},
                )
            return UtteranceOutcome(
                utterance.utterance_id,
                "failed",
                "unexpected_exception",
                f"unexpected exception in {current_stage}: {exc}",
                artifact_dir,
                {**durations, "traceback": 0.0},
            )


__all__ = ["BatchResult", "JapanMFAPipeline"]
