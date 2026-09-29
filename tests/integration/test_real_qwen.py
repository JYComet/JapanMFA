from __future__ import annotations

import os
import shlex
import wave
from dataclasses import dataclass
from pathlib import Path

import pytest

from japanmfa.asr.qwen3 import Qwen3ASRClient


pytestmark = pytest.mark.real_models

_REAL_QWEN_MAX_DURATION_SECONDS = 30.0
_REAL_QWEN_MAX_FILE_BYTES = 16 * 1024 * 1024


class _UnsupportedWavFormat(ValueError):
    """The opt-in fixture is not a supported PCM WAV file."""


@dataclass(frozen=True)
class _WavMetadata:
    channels: int
    sample_width: int
    sample_rate: int
    frames: int
    duration: float
    file_size: int


def _read_bounded_pcm_wav(
    path: Path,
    *,
    max_duration_seconds: float = _REAL_QWEN_MAX_DURATION_SECONDS,
    max_file_bytes: int = _REAL_QWEN_MAX_FILE_BYTES,
) -> _WavMetadata:
    """Read WAV header metadata and enforce the bounded real-model fixture contract."""
    if path.suffix.casefold() != ".wav":
        raise _UnsupportedWavFormat("Qwen audio fixture must have a .wav extension")
    try:
        file_size = path.stat().st_size
    except OSError as exc:
        raise _UnsupportedWavFormat(f"cannot stat WAV fixture: {path}") from exc
    if file_size <= 0:
        raise _UnsupportedWavFormat("WAV fixture is empty")
    if file_size > max_file_bytes:
        raise ValueError(
            f"WAV fixture is too large: {file_size} bytes > {max_file_bytes} byte bound"
        )

    try:
        with wave.open(str(path), "rb") as handle:
            channels = handle.getnchannels()
            sample_width = handle.getsampwidth()
            sample_rate = handle.getframerate()
            frames = handle.getnframes()
            compression = handle.getcomptype()
    except (EOFError, OSError, wave.Error) as exc:
        raise _UnsupportedWavFormat(f"unsupported WAV fixture format: {path}") from exc

    if compression != "NONE":
        raise _UnsupportedWavFormat(
            f"WAV fixture must use uncompressed PCM (got {compression!r})"
        )
    if channels <= 0 or sample_width not in {1, 2, 3, 4} or sample_rate <= 0:
        raise _UnsupportedWavFormat("WAV fixture has unsupported PCM metadata")
    if frames <= 0:
        raise ValueError("WAV fixture duration must be > 0 seconds")
    duration = frames / sample_rate
    if duration > max_duration_seconds:
        raise ValueError(
            f"WAV fixture duration is too long: {duration:.3f}s > "
            f"{max_duration_seconds:.3f}s bound"
        )
    return _WavMetadata(channels, sample_width, sample_rate, frames, duration, file_size)


def _write_pcm_wav(path: Path, *, frames: int, sample_rate: int = 16_000) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\0\0" * frames)


def test_bounded_wav_helper_validates_metadata_without_reading_audio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = tmp_path / "fixture.wav"
    _write_pcm_wav(audio, frames=16_000)
    monkeypatch.setattr(
        wave.Wave_read,
        "readframes",
        lambda *_args, **_kwargs: pytest.fail("WAV validation must not read audio frames"),
    )

    metadata = _read_bounded_pcm_wav(audio)

    assert metadata.channels == 1
    assert metadata.sample_width == 2
    assert metadata.sample_rate == 16_000
    assert metadata.frames == 16_000
    assert metadata.duration == pytest.approx(1.0)
    assert 0 < metadata.file_size <= _REAL_QWEN_MAX_FILE_BYTES


def test_bounded_wav_helper_enforces_duration_and_file_size_bounds(tmp_path: Path) -> None:
    audio = tmp_path / "fixture.wav"
    _write_pcm_wav(audio, frames=16_000)

    with pytest.raises(ValueError, match="duration is too long"):
        _read_bounded_pcm_wav(audio, max_duration_seconds=0.5)
    with pytest.raises(ValueError, match="too large"):
        _read_bounded_pcm_wav(audio, max_file_bytes=audio.stat().st_size - 1)


def test_bounded_wav_helper_rejects_unsupported_format(tmp_path: Path) -> None:
    audio = tmp_path / "fixture.wav"
    audio.write_bytes(b"not a wav")

    with pytest.raises(_UnsupportedWavFormat):
        _read_bounded_pcm_wav(audio)


def test_required_path_fails_when_opt_in_path_is_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    missing = tmp_path / "missing.wav"
    monkeypatch.setenv("JAPANMFA_REAL_QWEN_AUDIO", str(missing))

    with pytest.raises(AssertionError, match="does not point to a file"):
        _required_path("JAPANMFA_REAL_QWEN_AUDIO")


def test_required_path_skips_only_when_opt_in_variable_is_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JAPANMFA_REAL_QWEN_AUDIO", raising=False)

    with pytest.raises(pytest.skip.Exception):
        _required_path("JAPANMFA_REAL_QWEN_AUDIO")


def test_required_bounded_wav_fails_for_invalid_opt_in_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = tmp_path / "fixture.wav"
    audio.write_bytes(b"not a wav")
    monkeypatch.setenv("JAPANMFA_REAL_QWEN_AUDIO", str(audio))

    with pytest.raises(_UnsupportedWavFormat):
        _required_bounded_wav("JAPANMFA_REAL_QWEN_AUDIO")


def _required_path(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"set {name} to opt into the real Qwen test")
    path = Path(value).expanduser()
    if not path.is_file():
        raise AssertionError(f"{name} does not point to a file: {path}")
    return path.resolve()


def _required_bounded_wav(name: str) -> tuple[Path, _WavMetadata]:
    path = _required_path(name)
    return path, _read_bounded_pcm_wav(path)


def _worker_command() -> tuple[str, ...]:
    raw = os.environ.get("JAPANMFA_REAL_QWEN_COMMAND")
    if raw:
        command = tuple(shlex.split(raw))
        if command:
            return command
    runtime = os.environ.get("JAPANMFA_REAL_QWEN_PYTHON") or os.environ.get(
        "JAPANMFA_REAL_QWEN_RUNTIME"
    )
    if not runtime:
        pytest.skip(
            "set JAPANMFA_REAL_QWEN_COMMAND or JAPANMFA_REAL_QWEN_PYTHON "
            "to opt into the real Qwen test"
        )
    executable = Path(runtime).expanduser()
    if executable.is_dir():
        executable /= "bin/python"
    if not executable.is_file():
        pytest.skip(f"Qwen runtime does not point to an executable: {executable}")
    return (str(executable), "-m", "japanmfa.asr.worker")


def test_real_qwen_reports_japanese_for_bounded_audio() -> None:
    audio, metadata = _required_bounded_wav("JAPANMFA_REAL_QWEN_AUDIO")
    assert 0 < metadata.duration <= _REAL_QWEN_MAX_DURATION_SECONDS
    assert 0 < metadata.file_size <= _REAL_QWEN_MAX_FILE_BYTES
    model = os.environ.get("JAPANMFA_REAL_QWEN_MODEL")
    if not model:
        pytest.skip("set JAPANMFA_REAL_QWEN_MODEL to opt into the real Qwen test")
    model_path = Path(model).expanduser()
    if model_path.exists() and not model_path.is_dir():
        pytest.skip(f"JAPANMFA_REAL_QWEN_MODEL is not a model directory: {model_path}")

    aligner_model = os.environ.get("JAPANMFA_REAL_QWEN_ALIGNER_MODEL")
    if not aligner_model:
        pytest.skip("set JAPANMFA_REAL_QWEN_ALIGNER_MODEL to opt into Qwen timestamp verification")
    result = Qwen3ASRClient(
        _worker_command(), model=model, aligner_model=aligner_model
    ).transcribe([audio])[audio]

    assert result.language == "Japanese"
    assert result.text.strip()
    assert any("ぁ" <= character <= "龯" for character in result.text)
    assert result.lexical_timestamps
    assert all(item.start <= item.end for item in result.lexical_timestamps)
    assert all(item.source in {"lexical_gap", "boundary_point", "lexical_span"} for item in result.punctuation_timestamps)
