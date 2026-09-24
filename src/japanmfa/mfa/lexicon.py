"""Occurrence aliases and immutable MFA lexicon artifacts."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from japanmfa.domain import Pronunciation, Token
from japanmfa.errors import StageFailure
from japanmfa.frontend.mora import segment_morae


def _failure(reason_code: str, message: str, **details: object) -> StageFailure:
    return StageFailure("mfa_g2p", reason_code, message, details)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


@dataclass(frozen=True)
class LockedLexicon:
    """One utterance's occurrence-unique transcript and locked pronunciations."""

    utterance_id: str
    aliases: tuple[str, ...]
    transcript: str
    tokens: tuple[Token, ...]
    pronunciations: tuple[Pronunciation, ...]

    @classmethod
    def build(
        cls,
        utterance_id: str,
        tokens: tuple[Token, ...],
        pronunciations: tuple[Pronunciation, ...],
    ) -> "LockedLexicon":
        if not isinstance(utterance_id, str) or not utterance_id:
            raise _failure("invalid_utterance_id", "utterance_id must be non-empty")
        if len(tokens) != len(pronunciations):
            raise _failure(
                "count_mismatch",
                "tokens and pronunciations must have the same count",
                tokens=len(tokens),
                pronunciations=len(pronunciations),
            )

        for index, (token, pronunciation) in enumerate(zip(tokens, pronunciations)):
            if pronunciation.reading != token.reading:
                raise _failure(
                    "reading_mismatch",
                    "pronunciation reading must equal the locked token reading",
                    index=index,
                    token_reading=token.reading,
                    pronunciation_reading=pronunciation.reading,
                )
            if not pronunciation.phones or any(not variant or not all(variant) for variant in pronunciation.alternates):
                raise _failure(
                    "empty_pronunciation",
                    "each locked dictionary entry must contain at least one phone",
                    index=index,
                )

        aliases = tuple(f"jmfa_{index:06d}" for index in range(len(tokens)))
        return cls(
            utterance_id=utterance_id,
            aliases=aliases,
            transcript=" ".join(aliases),
            tokens=tuple(tokens),
            pronunciations=tuple(pronunciations),
        )

    def write(self, corpus_dir: Path, dictionary_path: Path) -> None:
        """Atomically publish this utterance's lab, dictionary, and audit mapping."""
        corpus_dir = Path(corpus_dir)
        dictionary_path = Path(dictionary_path)
        lab_path = corpus_dir / f"{self.utterance_id}.lab"
        audit_path = corpus_dir / "aliases.json"

        lab_content = f"{self.transcript}\n" if self.transcript else ""
        dictionary_content = "".join(
            f"{alias} {' '.join(phones)}\n"
            for alias, pronunciation in zip(self.aliases, self.pronunciations)
            for phones in (pronunciation.phones, *pronunciation.alternates)
        )

        audit: dict[str, dict[str, object]] = {}
        try:
            for alias, token, pronunciation in zip(
                self.aliases, self.tokens, self.pronunciations
            ):
                audit[alias] = {
                    "token_index": token.index,
                    "surface": token.surface,
                    "reading": token.reading,
                    "morae": [mora.kana for mora in segment_morae(token)],
                    "phones": list(pronunciation.phones),
                }
                if pronunciation.alternates:
                    audit[alias]["phone_variants"] = [list(variant) for variant in pronunciation.alternates]
            audit_content = json.dumps(
                audit, ensure_ascii=False, indent=2, sort_keys=True
            ) + "\n"
            _atomic_write(lab_path, lab_content)
            _atomic_write(dictionary_path, dictionary_content)
            _atomic_write(audit_path, audit_content)
        except (OSError, ValueError) as exc:
            if isinstance(exc, StageFailure):
                raise
            raise _failure(
                "artifact_write_failed",
                f"could not write locked MFA lexicon for {self.utterance_id}",
                utterance_id=self.utterance_id,
                error=str(exc),
            ) from exc
