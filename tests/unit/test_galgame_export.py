"""Output naming contract for the resumable Galgame export."""

from pathlib import Path

from tools.galgame_export import output_paths


def test_output_paths_preserve_dots_in_original_stem() -> None:
    wav, txt = output_paths(Path('/export'), Path('game/voice.v1.ogg'))

    assert wav == Path('/export/game/wav/voice.v1.wav')
    assert txt == Path('/export/game/txt/voice.v1.txt')
