import json
import re
import sys
from pathlib import Path

import pytest

from japanmfa.domain import Pronunciation
from japanmfa.errors import StageFailure
from japanmfa.mfa.g2p import MfaG2pClient


FAKE_MFA = Path(__file__).parents[1] / "fixtures" / "bin" / "fake_mfa.py"


def client() -> MfaG2pClient:
    return MfaG2pClient((sys.executable, str(FAKE_MFA)))


def test_g2p_writes_locked_wordlist_and_preserves_duplicate_positions(tmp_path: Path) -> None:
    argv_path = tmp_path / "argv.json"
    readings = ("キョウ", "ハレ", "キョウ")

    result = client().pronounce(readings, tmp_path / "work")

    assert result == (
        Pronunciation("キョウ", ("k", "jo", "N")),
        Pronunciation("ハレ", ("h", "a", "r", "e")),
        Pronunciation("キョウ", ("k", "jo", "N")),
    )
    input_path = tmp_path / "work" / "g2p_input.txt"
    assert input_path.read_text(encoding="utf-8") == "キョウ\nハレ\nキョウ\n"
    assert re.fullmatch(r".*/fake_mfa.py", str(FAKE_MFA))


def test_g2p_accepts_identical_duplicate_dictionary_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_MFA_MODE", "multiple")

    result = client().pronounce(("キョウ", "ハレ", "キョウ"), tmp_path / "multiple")

    assert result == (
        Pronunciation("キョウ", ("k", "jo", "N")),
        Pronunciation("ハレ", ("h", "a", "r", "e")),
        Pronunciation("キョウ", ("k", "jo", "N")),
    )


def test_g2p_preserves_distinct_model_pronunciation_candidates(tmp_path: Path) -> None:
    command = tmp_path / "variant_mfa.py"
    command.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "Path(sys.argv[4]).write_text(\n"
        "    'キョウ\\tk jo N\\nキョウ\\tk a N\\n', encoding='utf-8'\n"
        ")\n",
        encoding="utf-8",
    )

    result = MfaG2pClient((sys.executable, str(command))).pronounce(
        ("キョウ",), tmp_path / "variants"
    )
    assert result == (Pronunciation("キョウ", ("k", "jo", "N"), (("k", "a", "N"),)),)


@pytest.mark.parametrize("mode", ["missing", "oov", "mismatch"])
def test_g2p_rejects_incomplete_or_ambiguous_dictionary_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    monkeypatch.setenv("FAKE_MFA_MODE", mode)

    with pytest.raises(StageFailure) as exc_info:
        client().pronounce(("キョウ", "ハレ"), tmp_path / mode)

    assert exc_info.value.stage == "mfa_g2p"


def test_g2p_uses_expected_argv_without_shell(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    argv_path = tmp_path / "argv.json"
    monkeypatch.setenv("FAKE_MFA_ARGV", str(argv_path))

    client().pronounce(("キョウ",), tmp_path / "work")

    argv = json.loads(argv_path.read_text(encoding="utf-8"))
    assert argv[1] == "g2p"
    assert Path(argv[2]).name == "g2p_input.txt"
    assert argv[3] == "japanese_mfa"
    assert Path(argv[4]).name == "g2p_output.dict"
