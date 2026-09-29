"""Locate and inspect the project-owned native Qwen ForcedAligner checkpoint."""

from __future__ import annotations

import json
from pathlib import Path


DEFAULT_ALIGNER_MODEL = "Qwen/Qwen3-ForcedAligner-0.6B"


def local_native_aligner_dir() -> Path:
    return Path(__file__).resolve().parents[3] / ".runtime" / "models" / "qwen3-forced-aligner-0.6b"


def native_aligner_checkpoint_state(path: Path) -> str:
    if not path.is_dir():
        return "model_unavailable"
    config_path = path / "config.json"
    if not config_path.is_file():
        return "model_unavailable"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "model_incompatible"
    if (not isinstance(config, dict)
            or not isinstance(config.get("thinker_config"), dict)
            or config["thinker_config"].get("model_type") != "qwen3_forced_aligner"):
        return "model_incompatible"
    weights = (*path.glob("*.safetensors"), *path.glob("pytorch_model*.bin"))
    if not any(candidate.is_file() and candidate.stat().st_size > 0 for candidate in weights):
        return "model_unavailable"
    return "ok"
