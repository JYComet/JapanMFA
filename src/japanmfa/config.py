"""Typed YAML configuration for the JapanMFA pipeline."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
import math

import yaml


def _as_mapping(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def _reject_unknown(values: Mapping[str, Any], allowed: set[str], scope: str) -> None:
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise ValueError(f"unknown {scope} key(s): {', '.join(unknown)}")


def _string(value: Any, name: str, default: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _command(value: Any, name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ValueError(f"{name} must be a non-empty argument array")
    return tuple(value)


def _finite_nonnegative(value: Any, name: str, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite non-negative number")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name} must be a finite non-negative number")
    return result


@dataclass(frozen=True)
class ASRConfig:
    model: str = "Qwen/Qwen3-ASR-1.7B"
    fallback_model: str = "Qwen/Qwen3-ASR-0.6B"
    language: str = "Japanese"


@dataclass(frozen=True)
class MFAConfig:
    acoustic_model: str = "japanese_mfa"
    g2p_model: str = "japanese_mfa"
    dither: float = 0.0


@dataclass(frozen=True)
class AudioConfig:
    sample_rate: int = 16000
    max_silence_sec: float = 1.0
    sil_vol_threshold: float = 0.005
    sil_len_threshold: float = 0.08
    normalize_edges: bool = True
    target_edge_silence_sec: float = 0.5
    edge_silence_threshold: float = 0.001
    edge_frame_length: int = 1024


@dataclass(frozen=True)
class CommandConfig:
    ffmpeg: tuple[str, ...] = ("ffmpeg",)
    asr_worker: tuple[str, ...] = ("python", "-m", "japanmfa.asr.worker")
    mfa: tuple[str, ...] = ("mfa",)


@dataclass(frozen=True)
class PathConfig:
    cache_dir: Path = Path(".cache/japanmfa")
    output_dir: Path = Path("output")


@dataclass(frozen=True)
class ValidationConfig:
    silence_labels: tuple[str, ...] = ("", "sil", "sp", "spn", "<sp0>", "<sp1>", "<sp2>", "<sp3>")
    enable_word_in_silence_filter: bool = False


@dataclass(frozen=True)
class PipelineConfig:
    asr: ASRConfig = ASRConfig()
    mfa: MFAConfig = MFAConfig()
    audio: AudioConfig = AudioConfig()
    commands: CommandConfig = CommandConfig()
    paths: PathConfig = PathConfig()
    validation: ValidationConfig = ValidationConfig()

    @classmethod
    def load(cls, path: Path) -> "PipelineConfig":
        """Load and validate a YAML file, applying defaults for omitted values."""
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValueError(f"configuration file does not exist: {path}") from exc
        except yaml.YAMLError as exc:
            raise ValueError(f"invalid YAML configuration: {path}") from exc

        values = _as_mapping(raw, "configuration")
        sections = {"asr", "mfa", "audio", "commands", "paths", "validation"}
        _reject_unknown(values, sections, "top-level")

        asr_values = _as_mapping(values.get("asr"), "asr")
        _reject_unknown(asr_values, {"model", "fallback_model", "language"}, "asr")
        language = _string(asr_values.get("language"), "asr.language", "Japanese")
        if language != "Japanese":
            raise ValueError("asr.language must be Japanese")
        asr = ASRConfig(
            model=_string(asr_values.get("model"), "asr.model", ASRConfig.model),
            fallback_model=_string(
                asr_values.get("fallback_model"),
                "asr.fallback_model",
                ASRConfig.fallback_model,
            ),
            language=language,
        )

        mfa_values = _as_mapping(values.get("mfa"), "mfa")
        _reject_unknown(mfa_values, {"acoustic_model", "g2p_model", "dither"}, "mfa")
        mfa = MFAConfig(
            acoustic_model=_string(
                mfa_values.get("acoustic_model"),
                "mfa.acoustic_model",
                MFAConfig.acoustic_model,
            ),
            g2p_model=_string(
                mfa_values.get("g2p_model"), "mfa.g2p_model", MFAConfig.g2p_model
            ),
            dither=_finite_nonnegative(mfa_values.get("dither"), "mfa.dither", MFAConfig.dither),
        )

        audio_values = _as_mapping(values.get("audio"), "audio")
        _reject_unknown(audio_values, {"sample_rate", "max_silence_sec", "sil_vol_threshold",
                                       "sil_len_threshold", "normalize_edges",
                                       "target_edge_silence_sec", "edge_silence_threshold",
                                       "edge_frame_length"}, "audio")
        sample_rate = audio_values.get("sample_rate", AudioConfig.sample_rate)
        if isinstance(sample_rate, bool) or not isinstance(sample_rate, int) or sample_rate <= 0:
            raise ValueError("audio.sample_rate must be a positive integer")
        normalize_edges = audio_values.get("normalize_edges", AudioConfig.normalize_edges)
        if not isinstance(normalize_edges, bool):
            raise ValueError("audio.normalize_edges must be a boolean")
        edge_frame_length = audio_values.get("edge_frame_length", AudioConfig.edge_frame_length)
        if isinstance(edge_frame_length, bool) or not isinstance(edge_frame_length, int) or edge_frame_length <= 0:
            raise ValueError("audio.edge_frame_length must be a positive integer")
        audio = AudioConfig(
            sample_rate=sample_rate,
            max_silence_sec=_finite_nonnegative(audio_values.get("max_silence_sec"), "audio.max_silence_sec", AudioConfig.max_silence_sec),
            sil_vol_threshold=_finite_nonnegative(audio_values.get("sil_vol_threshold"), "audio.sil_vol_threshold", AudioConfig.sil_vol_threshold),
            sil_len_threshold=_finite_nonnegative(audio_values.get("sil_len_threshold"), "audio.sil_len_threshold", AudioConfig.sil_len_threshold),
            normalize_edges=normalize_edges,
            target_edge_silence_sec=_finite_nonnegative(audio_values.get("target_edge_silence_sec"), "audio.target_edge_silence_sec", AudioConfig.target_edge_silence_sec),
            edge_silence_threshold=_finite_nonnegative(audio_values.get("edge_silence_threshold"), "audio.edge_silence_threshold", AudioConfig.edge_silence_threshold),
            edge_frame_length=edge_frame_length,
        )

        command_values = _as_mapping(values.get("commands"), "commands")
        _reject_unknown(command_values, {"ffmpeg", "asr_worker", "mfa"}, "commands")
        commands = CommandConfig(
            ffmpeg=_command(command_values.get("ffmpeg"), "commands.ffmpeg", CommandConfig.ffmpeg),
            asr_worker=_command(
                command_values.get("asr_worker"),
                "commands.asr_worker",
                CommandConfig.asr_worker,
            ),
            mfa=_command(command_values.get("mfa"), "commands.mfa", CommandConfig.mfa),
        )

        path_values = _as_mapping(values.get("paths"), "paths")
        _reject_unknown(path_values, {"cache_dir", "output_dir"}, "paths")
        paths = PathConfig(
            cache_dir=Path(
                _string(path_values.get("cache_dir"), "paths.cache_dir", str(PathConfig.cache_dir))
            ),
            output_dir=Path(
                _string(path_values.get("output_dir"), "paths.output_dir", str(PathConfig.output_dir))
            ),
        )

        validation_values = _as_mapping(values.get("validation"), "validation")
        _reject_unknown(validation_values, {"silence_labels", "enable_word_in_silence_filter"}, "validation")
        silence_labels = validation_values.get(
            "silence_labels", ValidationConfig.silence_labels
        )
        if not isinstance(silence_labels, (list, tuple)) or not all(
            isinstance(label, str) for label in silence_labels
        ):
            raise ValueError("validation.silence_labels must be a string array")
        enable_word_filter = validation_values.get(
            "enable_word_in_silence_filter", ValidationConfig.enable_word_in_silence_filter
        )
        if not isinstance(enable_word_filter, bool):
            raise ValueError("validation.enable_word_in_silence_filter must be a boolean")
        validation = ValidationConfig(
            silence_labels=tuple(silence_labels),
            enable_word_in_silence_filter=enable_word_filter,
        )

        return cls(
            asr=asr,
            mfa=mfa,
            audio=audio,
            commands=commands,
            paths=paths,
            validation=validation,
        )
