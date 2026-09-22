import json
import re
from pathlib import Path

import pytest

from japanmfa.domain import Pronunciation, Token
from japanmfa.errors import StageFailure
from japanmfa.mfa.lexicon import LockedLexicon


def token(index: int, surface: str = "今日", reading: str = "キョウ") -> Token:
    return Token(index, index, index + len(surface), surface, ("名詞",), reading, "sudachi")


def test_aliases_are_unique_per_occurrence() -> None:
    lexicon = LockedLexicon.build(
        "speaker/001",
        (token(0), token(1)),
        (Pronunciation("キョウ", ("k", "jo", "N")),) * 2,
    )

    assert lexicon.aliases == ("jmfa_000000", "jmfa_000001")
    assert lexicon.transcript == "jmfa_000000 jmfa_000001"
    assert len(set(lexicon.aliases)) == 2
    assert all(re.fullmatch(r"[a-z0-9_]", char) for alias in lexicon.aliases for char in alias)


def test_locked_lexicon_writes_lab_dictionary_and_audit_sidecar(tmp_path: Path) -> None:
    lexicon = LockedLexicon.build(
        "speaker/001",
        (token(0), token(1, "晴れ", "ハレ")),
        (
            Pronunciation("キョウ", ("k", "jo", "N")),
            Pronunciation("ハレ", ("h", "a", "r", "e")),
        ),
    )
    dictionary = tmp_path / "dict" / "lexicon.dict"

    lexicon.write(tmp_path / "corpus", dictionary)

    lab = tmp_path / "corpus" / "speaker" / "001.lab"
    assert lab.read_text(encoding="utf-8") == "jmfa_000000 jmfa_000001\n"
    assert dictionary.read_text(encoding="utf-8") == (
        "jmfa_000000 k jo N\n" "jmfa_000001 h a r e\n"
    )
    audit = tmp_path / "corpus" / "aliases.json"
    payload = json.loads(audit.read_text(encoding="utf-8"))
    assert payload["jmfa_000000"] == {
        "token_index": 0,
        "surface": "今日",
        "reading": "キョウ",
        "morae": ["キョ", "ウ"],
        "phones": ["k", "jo", "N"],
    }


@pytest.mark.parametrize(
    ("tokens", "pronunciations"),
    [
        ((token(0),), ()),
        ((token(0),), (Pronunciation("ハレ", ("h",)),)),
    ],
)
def test_locked_lexicon_rejects_count_or_reading_mismatch(
    tokens: tuple[Token, ...], pronunciations: tuple[Pronunciation, ...]
) -> None:
    with pytest.raises(StageFailure) as exc_info:
        LockedLexicon.build("speaker/001", tokens, pronunciations)

    assert exc_info.value.stage == "mfa_g2p"
