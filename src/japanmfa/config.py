"""Typed YAML configuration for the JapanMFA pipeline."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

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


@dataclass(frozen=True)
class ASRConfig:
    model: str = "Qwen/Qwen3-ASR-1.7B"
    fallback_model: str = "Qwen/Qwen3-ASR-0.6B"
    language: str = "Japanese"


@dataclass(frozen=True)
class MFAConfig:
    acoustic_model: str = "japanese_mfa"
    g2p_model: str = "japanese_mfa"


@dataclass(frozen=True)
class AudioConfig:
    sample_rate: int = 16000


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
    silence_labels: tuple[str, ...] = ("", "sil", "sp", "spn")


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
        _reject_unknown(mfa_values, {"acoustic_model", "g2p_model"}, "mfa")
        mfa = MFAConfig(
            acoustic_model=_string(
                mfa_values.get("acoustic_model"),
                "mfa.acoustic_model",
                MFAConfig.acoustic_model,
            ),
            g2p_model=_string(
                mfa_values.get("g2p_model"), "mfa.g2p_model", MFAConfig.g2p_model
            ),
        )

        audio_values = _as_mapping(values.get("audio"), "audio")
        _reject_unknown(audio_values, {"sample_rate"}, "audio")
        sample_rate = audio_values.get("sample_rate", AudioConfig.sample_rate)
        if isinstance(sample_rate, bool) or not isinstance(sample_rate, int) or sample_rate <= 0:
            raise ValueError("audio.sample_rate must be a positive integer")
        audio = AudioConfig(sample_rate=sample_rate)

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
        _reject_unknown(validation_values, {"silence_labels"}, "validation")
        silence_labels = validation_values.get(
            "silence_labels", ValidationConfig.silence_labels
        )
        if not isinstance(silence_labels, (list, tuple)) or not all(
            isinstance(label, str) for label in silence_labels
        ):
            raise ValueError("validation.silence_labels must be a string array")
        validation = ValidationConfig(silence_labels=tuple(silence_labels))

        return cls(
            asr=asr,
            mfa=mfa,
            audio=audio,
            commands=commands,
            paths=paths,
            validation=validation,
        )
