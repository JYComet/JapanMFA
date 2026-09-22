"""Safe FFmpeg conversion into a normalized working audio copy."""

import os
import stat
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

from .config import PipelineConfig
from .errors import StageFailure


@dataclass(frozen=True)
class AudioInfo:
    source_path: Path
    working_path: Path
    duration: float
    source_sample_rate: int
    source_channels: int
    working_sample_rate: int


def _source_metadata(path: Path) -> tuple[float, int, int]:
    """Read common WAV metadata without requiring an external probe utility."""
    try:
        with wave.open(str(path), "rb") as wav:
            sample_rate = wav.getframerate()
            frames = wav.getnframes()
            duration = frames / sample_rate if sample_rate else 0.0
            return duration, sample_rate, wav.getnchannels()
    except (EOFError, OSError, wave.Error):
        # FFmpeg remains authoritative for decoding; metadata is unavailable
        # for inputs that are not readable by Python's WAV reader.
        return 0.0, 0, 0


def _cleanup_partial(partial: Path) -> str | None:
    """Best-effort cleanup; return an error without masking the primary failure."""
    try:
        partial.unlink(missing_ok=True)
    except OSError as exc:
        return str(exc)
    return None


class AudioNormalizer:
    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.config = config or PipelineConfig()

    def prepare(self, source: Path, destination: Path) -> AudioInfo:
        source = Path(source)
        destination = Path(destination)
        partial = destination.with_suffix(".partial.wav")
        duration, source_sample_rate, source_channels = _source_metadata(source)
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StageFailure(
                "audio",
                "destination_directory_failed",
                f"could not prepare audio destination directory: {destination.parent}",
                {"destination": str(destination), "error": str(exc)},
            ) from exc

        try:
            partial.unlink(missing_ok=True)
        except OSError as exc:
            raise StageFailure(
                "audio",
                "partial_cleanup_failed",
                f"could not remove stale partial audio: {partial}",
                {"partial": str(partial), "error": str(exc)},
            ) from exc

        argv = [
            *self.config.commands.ffmpeg,
            "-nostdin",
            "-y",
            "-i",
            str(source),
            "-ac",
            "1",
            "-ar",
            str(self.config.audio.sample_rate),
            "-c:a",
            "pcm_s16le",
            str(partial),
        ]
        try:
            subprocess.run(argv, check=True, capture_output=True, text=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            cleanup_error = _cleanup_partial(partial)
            stderr = getattr(exc, "stderr", None)
            details = {
                "source": str(source),
                "destination": str(destination),
                "returncode": getattr(exc, "returncode", None),
                "stderr": stderr or str(exc),
            }
            if cleanup_error is not None:
                details["partial_cleanup_error"] = cleanup_error
            raise StageFailure(
                "audio",
                "ffmpeg_failed",
                f"ffmpeg failed while normalizing {source}",
                details,
            ) from exc

        try:
            partial_stat = partial.stat()
        except OSError as exc:
            cleanup_error = _cleanup_partial(partial)
            details = {"source": str(source), "destination": str(destination), "error": str(exc)}
            if cleanup_error is not None:
                details["partial_cleanup_error"] = cleanup_error
            raise StageFailure(
                "audio",
                "output_stat_failed",
                f"could not inspect working audio: {partial}",
                details,
            ) from exc

        if not stat.S_ISREG(partial_stat.st_mode) or partial_stat.st_size == 0:
            cleanup_error = _cleanup_partial(partial)
            details = {"source": str(source), "destination": str(destination)}
            if cleanup_error is not None:
                details["partial_cleanup_error"] = cleanup_error
            raise StageFailure(
                "audio",
                "empty_output",
                f"ffmpeg produced no working audio: {partial}",
                details,
            )

        try:
            os.replace(partial, destination)
        except OSError as exc:
            cleanup_error = _cleanup_partial(partial)
            details = {"source": str(source), "destination": str(destination), "error": str(exc)}
            if cleanup_error is not None:
                details["partial_cleanup_error"] = cleanup_error
            raise StageFailure(
                "audio",
                "atomic_replace_failed",
                f"could not publish working audio: {destination}",
                details,
            ) from exc

        return AudioInfo(
            source_path=source,
            working_path=destination,
            duration=duration,
            source_sample_rate=source_sample_rate,
            source_channels=source_channels,
            working_sample_rate=self.config.audio.sample_rate,
        )
