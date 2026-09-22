import json
import sys
import wave
from pathlib import Path

import pytest

import japanmfa.audio as audio_module
from japanmfa.audio import AudioNormalizer
from japanmfa.config import CommandConfig, PipelineConfig
from japanmfa.errors import StageFailure


def write_wav(path: Path, *, sample_rate: int = 8000, channels: int = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\0\0" * (channels * sample_rate // 10))


def test_ffmpeg_contract_uses_safe_argument_array_and_publishes_working_audio(
    tmp_path: Path, monkeypatch, request
) -> None:
    source = tmp_path / "source.wav"
    destination = tmp_path / "working.wav"
    argv_record = tmp_path / "ffmpeg-argv.json"
    write_wav(source)
    fake_ffmpeg = Path(request.fspath).parents[1] / "fixtures" / "bin" / "fake_ffmpeg.py"
    monkeypatch.setenv("FAKE_FFMPEG_ARGV_RECORD", str(argv_record))

    config = PipelineConfig(
        commands=CommandConfig(ffmpeg=(sys.executable, str(fake_ffmpeg)))
    )
    info = AudioNormalizer(config).prepare(source, destination)

    argv = json.loads(argv_record.read_text(encoding="utf-8"))
    assert "-nostdin" in argv
    assert "-ac" in argv and argv[argv.index("-ac") + 1] == "1"
    assert "-ar" in argv and argv[argv.index("-ar") + 1] == "16000"
    assert "-c:a" in argv and argv[argv.index("-c:a") + 1] == "pcm_s16le"
    assert str(source) in argv
    partial = destination.with_suffix(".partial.wav")
    assert str(partial) in argv
    assert destination.exists()
    assert destination.stat().st_size > 0
    assert info.source_path == source
    assert info.working_path == destination
    assert info.source_sample_rate == 8000
    assert info.source_channels == 2
    assert info.working_sample_rate == 16000
    assert info.duration == 0.1


def test_destination_directory_failure_is_typed(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.wav"
    destination = tmp_path / "new" / "working.wav"
    write_wav(source)
    original_mkdir = Path.mkdir

    def fail_destination_mkdir(self: Path, *args, **kwargs) -> None:
        if self == destination.parent:
            raise OSError("read-only destination")
        original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_destination_mkdir)

    with pytest.raises(StageFailure) as exc_info:
        AudioNormalizer().prepare(source, destination)

    assert exc_info.value.stage == "audio"
    assert exc_info.value.reason_code == "destination_directory_failed"


def test_atomic_replace_failure_is_typed_and_cleans_partial(
    tmp_path: Path, monkeypatch, request
) -> None:
    source = tmp_path / "source.wav"
    destination = tmp_path / "working.wav"
    write_wav(source)
    fake_ffmpeg = Path(request.fspath).parents[1] / "fixtures" / "bin" / "fake_ffmpeg.py"
    config = PipelineConfig(
        commands=CommandConfig(ffmpeg=(sys.executable, str(fake_ffmpeg)))
    )
    partial = destination.with_suffix(".partial.wav")

    def fail_replace(source_path: Path, destination_path: Path) -> None:
        assert source_path == partial
        assert destination_path == destination
        raise OSError("cross-device rename")

    monkeypatch.setattr(audio_module.os, "replace", fail_replace)

    with pytest.raises(StageFailure) as exc_info:
        AudioNormalizer(config).prepare(source, destination)

    assert exc_info.value.stage == "audio"
    assert exc_info.value.reason_code == "atomic_replace_failed"
    assert not partial.exists()


def test_output_stat_failure_is_typed_and_cleans_partial(
    tmp_path: Path, monkeypatch, request
) -> None:
    source = tmp_path / "source.wav"
    destination = tmp_path / "working.wav"
    write_wav(source)
    fake_ffmpeg = Path(request.fspath).parents[1] / "fixtures" / "bin" / "fake_ffmpeg.py"
    config = PipelineConfig(
        commands=CommandConfig(ffmpeg=(sys.executable, str(fake_ffmpeg)))
    )
    partial = destination.with_suffix(".partial.wav")
    original_stat = Path.stat

    def fail_partial_stat(self: Path, *args, **kwargs):
        if self == partial:
            raise OSError("metadata unavailable")
        return original_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", fail_partial_stat)

    with pytest.raises(StageFailure) as exc_info:
        AudioNormalizer(config).prepare(source, destination)

    assert exc_info.value.stage == "audio"
    assert exc_info.value.reason_code == "output_stat_failed"
    monkeypatch.undo()
    assert not partial.exists()
