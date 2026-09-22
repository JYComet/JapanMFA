from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from japanmfa.errors import StageFailure
from japanmfa.mfa.runner import MfaRunner


FAKE_MFA = Path(__file__).parents[1] / "fixtures" / "bin" / "fake_mfa.py"


def _runner() -> MfaRunner:
    return MfaRunner((sys.executable, str(FAKE_MFA)))


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "001.lab").write_text("jmfa_000000\n", encoding="utf-8")
    dictionary = tmp_path / "dictionary.dict"
    dictionary.write_text("jmfa_000000 k a\n", encoding="utf-8")
    output = tmp_path / "output"
    work = tmp_path / "utterance-work"
    return corpus, dictionary, output, work


def test_align_validates_first_and_uses_pinned_mfa_3_argv(tmp_path: Path, monkeypatch) -> None:
    corpus, dictionary, output, work = _inputs(tmp_path)
    argv_log = tmp_path / "argv.jsonl"
    monkeypatch.setenv("FAKE_MFA_ARGV_LOG", str(argv_log))

    textgrid = _runner().align(corpus, dictionary, output, work)

    assert textgrid == output / "aligned.TextGrid"
    commands = [json.loads(line) for line in argv_log.read_text().splitlines()]
    assert commands[0][1:6] == [
        "validate",
        str(corpus),
        str(dictionary),
        "japanese_mfa",
        "--output_directory",
    ]
    assert commands[0][-1] == str(work)
    assert commands[1][1:6] == [
        "align",
        str(corpus),
        str(dictionary),
        "japanese_mfa",
        str(output),
    ]
    assert commands[1][6:] == ["--temporary_directory", str(work), "--clean"]
    assert (work / "validate.stdout.log").read_text(encoding="utf-8") == "validated\n"
    assert (work / "align.stderr.log").read_text(encoding="utf-8") == ""


def test_nonzero_mfa_exit_preserves_stderr_and_skips_alignment(tmp_path: Path, monkeypatch) -> None:
    corpus, dictionary, output, work = _inputs(tmp_path)
    argv_log = tmp_path / "argv.jsonl"
    monkeypatch.setenv("FAKE_MFA_ARGV_LOG", str(argv_log))
    monkeypatch.setenv("FAKE_MFA_MODE", "validate_fail")

    with pytest.raises(StageFailure) as exc_info:
        _runner().align(corpus, dictionary, output, work)

    failure = exc_info.value
    assert (failure.stage, failure.reason_code) == ("mfa", "command_failed")
    assert "validation failed" in str(failure.details["stderr"])
    assert (work / "validate.stderr.log").read_text(encoding="utf-8") == "validation failed\n"
    assert len(argv_log.read_text(encoding="utf-8").splitlines()) == 1


def test_missing_alignment_textgrid_is_typed(tmp_path: Path, monkeypatch) -> None:
    corpus, dictionary, output, work = _inputs(tmp_path)
    monkeypatch.setenv("FAKE_MFA_MODE", "missing_output")

    with pytest.raises(StageFailure) as exc_info:
        _runner().align(corpus, dictionary, output, work)

    assert (exc_info.value.stage, exc_info.value.reason_code) == (
        "mfa",
        "missing_output",
    )
