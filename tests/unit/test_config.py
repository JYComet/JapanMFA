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
    assert config.asr.aligner_model == "Qwen/Qwen3-ForcedAligner-0.6B"
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


@pytest.mark.parametrize("value", [True, -0.1, float("nan"), float("inf")])
def test_config_rejects_invalid_mfa_dither(tmp_path: Path, value: float) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(f"mfa:\n  dither: {value!r}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="mfa.dither"):
        PipelineConfig.load(path)


def test_config_defaults_mfa_dither_to_model_value(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("mfa: {}\n", encoding="utf-8")
    assert PipelineConfig.load(path).mfa.dither == 1.0


def test_audio_preprocess_defaults_are_upstream_values() -> None:
    config = PipelineConfig()
    assert config.audio.max_silence_sec == 1.0
    assert config.audio.sil_vol_threshold == .005
    assert config.audio.sil_len_threshold == .08
    assert config.audio.normalize_edges is True
    assert config.audio.target_edge_silence_sec == .5
    assert config.audio.edge_silence_threshold == .001
    assert config.audio.edge_frame_length == 1024


def test_config_accepts_custom_qwen_aligner_model(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("asr:\n  aligner_model: local/ja-aligner\n", encoding="utf-8")
    assert PipelineConfig.load(path).asr.aligner_model == "local/ja-aligner"
