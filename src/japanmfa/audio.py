"""Safe FFmpeg conversion into a normalized working audio copy."""

import os
import stat
import subprocess
import wave
import hashlib
import numpy as np
import soundfile
from dataclasses import dataclass
from pathlib import Path

from .config import PipelineConfig
from .errors import StageFailure
from .postprocess import trim_excessive_silence, normalize_start_end_silence


@dataclass(frozen=True)
class AudioInfo:
    source_path: Path
    working_path: Path
    duration: float
    source_sample_rate: int
    source_channels: int
    working_sample_rate: int
    source_frames: int = 0
    working_frames: int = 0
    source_sha256: str = ""
    working_sha256: str = ""


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
            source_audio, source_sample_rate = soundfile.read(str(source), always_2d=False)
            source_channels = int(source_audio.shape[1]) if getattr(source_audio, "ndim", 1) > 1 else 1
            if getattr(source_audio, "ndim", 1) > 1:
                source_audio = source_audio[:, 0]
            source_audio = np.asarray(source_audio)
            source_frames = int(len(source_audio))
            duration = source_frames / source_sample_rate if source_sample_rate else 0.0
            processed_audio = trim_excessive_silence(
                source_audio, source_sample_rate,
                max_silence_sec=self.config.audio.max_silence_sec,
                sil_vol_threshold=self.config.audio.sil_vol_threshold,
                sil_len_threshold=self.config.audio.sil_len_threshold,
            )
            if self.config.audio.normalize_edges:
                processed_audio = normalize_start_end_silence(
                    processed_audio, source_sample_rate,
                    target_silence_sec=self.config.audio.target_edge_silence_sec,
                    silence_threshold=self.config.audio.edge_silence_threshold,
                    frame_length=self.config.audio.edge_frame_length,
                )
        except (OSError, RuntimeError, ValueError) as exc:
            raise StageFailure("audio", "native_preprocess_failed", f"could not preprocess {source}", {"error": str(exc)}) from exc
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
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

        native_partial = destination.with_suffix(".native.partial.wav")
        try:
            soundfile.write(str(native_partial), processed_audio, source_sample_rate)
        except (OSError, RuntimeError, ValueError) as exc:
            raise StageFailure("audio", "native_preprocess_write_failed", f"could not write native intermediate: {native_partial}", {"error": str(exc)}) from exc
        argv = [
            *self.config.commands.ffmpeg,
            "-nostdin",
            "-y",
            "-i",
            str(native_partial),
            "-metadata",
            f"comment=japanmfa-source:{source}",
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
            try:
                native_partial.unlink(missing_ok=True)
            except OSError:
                pass
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
            native_partial.unlink(missing_ok=True)
        except OSError:
            pass

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

        try:
            with wave.open(str(destination), "rb") as working_wave:
                working_frames = working_wave.getnframes()
                working_rate = working_wave.getframerate()
        except (EOFError, OSError, wave.Error):
            # Lightweight command doubles may only publish a sentinel. Real
            # FFmpeg outputs are always validated by the pipeline cache.
            working_frames = 0
            working_rate = self.config.audio.sample_rate
        working_hash = hashlib.sha256(destination.read_bytes()).hexdigest()
        return AudioInfo(
            source_path=source,
            working_path=destination,
            duration=duration,
            source_sample_rate=source_sample_rate,
            source_channels=source_channels,
            working_sample_rate=working_rate,
            source_frames=source_frames,
            working_frames=working_frames,
            source_sha256=source_hash,
            working_sha256=working_hash,
        )
