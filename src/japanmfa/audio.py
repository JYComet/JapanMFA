"""Safe FFmpeg conversion into a normalized working audio copy."""

import os
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


class AudioNormalizer:
    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.config = config or PipelineConfig()

    def prepare(self, source: Path, destination: Path) -> AudioInfo:
        source = Path(source)
        destination = Path(destination)
        partial = destination.with_suffix(".partial.wav")
        duration, source_sample_rate, source_channels = _source_metadata(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial.unlink(missing_ok=True)

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
            partial.unlink(missing_ok=True)
            stderr = getattr(exc, "stderr", None)
            raise StageFailure(
                "audio",
                "ffmpeg_failed",
                f"ffmpeg failed while normalizing {source}",
                {
                    "source": str(source),
                    "destination": str(destination),
                    "returncode": getattr(exc, "returncode", None),
                    "stderr": stderr or str(exc),
                },
            ) from exc

        if not partial.is_file() or partial.stat().st_size == 0:
            partial.unlink(missing_ok=True)
            raise StageFailure(
                "audio",
                "empty_output",
                f"ffmpeg produced no working audio: {partial}",
                {"source": str(source), "destination": str(destination)},
            )

        os.replace(partial, destination)
        return AudioInfo(
            source_path=source,
            working_path=destination,
            duration=duration,
            source_sample_rate=source_sample_rate,
            source_channels=source_channels,
            working_sample_rate=self.config.audio.sample_rate,
        )
