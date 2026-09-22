import json
import sys
import wave
from pathlib import Path

from japanmfa.audio import AudioNormalizer
from japanmfa.config import CommandConfig, PipelineConfig


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
