"""Read-only discovery and text loading for Japanese corpus inputs."""

import unicodedata
from pathlib import Path

from .domain import SourceText, Utterance
from .errors import StageFailure


def discover_utterances(root: Path) -> list[Utterance]:
    """Discover lowercase ``.wav`` files in deterministic relative-path order.

    The returned paths remain rooted at the caller-provided path.  Resolution is
    used only when reporting comparison details; discovery never writes to the
    corpus.
    """
    root = Path(root)
    candidates = sorted(
        root.rglob("*.wav"),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    utterances: list[Utterance] = []
    seen_ids: dict[str, tuple[str, Path]] = {}

    for audio_path in candidates:
        if audio_path.is_symlink():
            raise StageFailure(
                "discovery",
                "symlink_audio",
                f"symlinked audio is not allowed: {audio_path}",
                {"path": str(audio_path), "resolved_path": str(audio_path.resolve())},
            )

        relative_audio = audio_path.relative_to(root)
        utterance_id = relative_audio.with_suffix("").as_posix()
        folded_id = utterance_id.casefold()
        previous = seen_ids.get(folded_id)
        if previous is not None:
            raise StageFailure(
                "discovery",
                "duplicate_utterance_id",
                f"utterance id collision: {previous[0]} and {utterance_id}",
                {
                    "utterance_id": utterance_id,
                    "paths": (str(previous[1]), str(audio_path)),
                    "resolved_paths": (
                        str(previous[1].resolve()),
                        str(audio_path.resolve()),
                    ),
                },
            )
        seen_ids[folded_id] = (utterance_id, audio_path)

        text_path = audio_path.with_suffix(".txt")
        utterances.append(
            Utterance(
                utterance_id=utterance_id,
                audio_path=audio_path,
                text_path=text_path if text_path.is_file() else None,
            )
        )

    return utterances


def load_source_text(path: Path) -> SourceText:
    """Load UTF-8 source text and derive its one-utterance processing copy."""
    path = Path(path)
    try:
        decoded = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StageFailure(
            "text",
            "invalid_utf8",
            f"source text is not valid UTF-8: {path}",
            {"path": str(path)},
        ) from exc

    if decoded.startswith("\ufeff"):
        decoded = decoded[1:]
    processing = unicodedata.normalize(
        "NFC", decoded.replace("\r\n", "").replace("\n", "").replace("\r", "").strip()
    )
    return SourceText(original=decoded, processing=processing, source="txt")
