from pathlib import Path

import pytest

from japanmfa.config import PipelineConfig


def test_default_config_locks_required_models(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "asr:\n  model: Qwen/Qwen3-ASR-1.7B\n  language: Japanese\n"
        "mfa:\n  acoustic_model: japanese_mfa\n  g2p_model: japanese_mfa\n"
        "audio:\n  sample_rate: 16000\n",
        encoding="utf-8",
    )

    config = PipelineConfig.load(path)

    assert config.asr.language == "Japanese"
    assert config.asr.model == "Qwen/Qwen3-ASR-1.7B"
    assert config.mfa.acoustic_model == "japanese_mfa"
    assert config.mfa.g2p_model == "japanese_mfa"
    assert config.audio.sample_rate == 16000


def test_config_rejects_unknown_top_level_key(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("asr: {}\nunknown: {}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unknown top-level"):
        PipelineConfig.load(path)


def test_config_rejects_non_japanese_language(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("asr:\n  language: English\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Japanese"):
        PipelineConfig.load(path)


def test_external_commands_are_argument_arrays(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "commands:\n  ffmpeg: [ffmpeg]\n  asr_worker: [python, worker.py]\n",
        encoding="utf-8",
    )

    config = PipelineConfig.load(path)

    assert config.commands.ffmpeg == ("ffmpeg",)
    assert config.commands.asr_worker == ("python", "worker.py")
