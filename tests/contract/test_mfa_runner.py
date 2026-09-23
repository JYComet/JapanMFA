from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from japanmfa.errors import StageFailure
from japanmfa.mfa.runner import MfaRunner


FAKE_MFA = Path(__file__).parents[1] / "fixtures" / "bin" / "fake_mfa.py"


def _runner(owned_root: Path) -> MfaRunner:
    return MfaRunner((sys.executable, str(FAKE_MFA)), owned_root=owned_root)


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    owned_root = tmp_path / "owned-root"
    owned_root.mkdir()
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "001.lab").write_text("jmfa_000000\n", encoding="utf-8")
    dictionary = tmp_path / "dictionary.dict"
    dictionary.write_text("jmfa_000000 k a\n", encoding="utf-8")
    output = owned_root / "output"
    work = owned_root / "utterance-work"
    return corpus, dictionary, output, work, owned_root


def test_align_validates_first_and_uses_pinned_mfa_3_argv(tmp_path: Path, monkeypatch) -> None:
    corpus, dictionary, output, work, owned_root = _inputs(tmp_path)
    argv_log = tmp_path / "argv.jsonl"
    monkeypatch.setenv("FAKE_MFA_ARGV_LOG", str(argv_log))

    textgrid = _runner(owned_root).align(corpus, dictionary, output, work)

    assert textgrid == output / "aligned.TextGrid"
    commands = [json.loads(line) for line in argv_log.read_text().splitlines()]
    assert commands[0][1:5] == [
        "validate",
        str(corpus),
        str(dictionary),
        "japanese_mfa",
    ]
    assert commands[0][5:] == [
        "--ignore_acoustics",
        "--output_directory",
        str(work),
        "--temporary_directory",
        str(work / "validate_temp"),
        "--clean",
    ]
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
    corpus, dictionary, output, work, owned_root = _inputs(tmp_path)
    argv_log = tmp_path / "argv.jsonl"
    monkeypatch.setenv("FAKE_MFA_ARGV_LOG", str(argv_log))
    monkeypatch.setenv("FAKE_MFA_MODE", "validate_fail")

    with pytest.raises(StageFailure) as exc_info:
        _runner(owned_root).align(corpus, dictionary, output, work)

    failure = exc_info.value
    assert (failure.stage, failure.reason_code) == ("mfa", "command_failed")
    assert "validation failed" in str(failure.details["stderr"])
    assert (work / "validate.stderr.log").read_text(encoding="utf-8") == "validation failed\n"
    assert len(argv_log.read_text(encoding="utf-8").splitlines()) == 1


def test_missing_alignment_textgrid_is_typed(tmp_path: Path, monkeypatch) -> None:
    corpus, dictionary, output, work, owned_root = _inputs(tmp_path)
    monkeypatch.setenv("FAKE_MFA_MODE", "missing_output")

    with pytest.raises(StageFailure) as exc_info:
        _runner(owned_root).align(corpus, dictionary, output, work)

    assert (exc_info.value.stage, exc_info.value.reason_code) == (
        "mfa",
        "missing_output",
    )


def test_timeout_bytes_are_decoded_logged_and_typed(
    tmp_path: Path, monkeypatch
) -> None:
    corpus, dictionary, _output, work, owned_root = _inputs(tmp_path)
    timeout = subprocess.TimeoutExpired(
        ["mfa", "validate"], 1, output=b"partial stdout \xff", stderr=b"partial stderr \xfe"
    )
    monkeypatch.setattr("japanmfa.mfa.runner.subprocess.run", lambda *args, **kwargs: (_ for _ in ()).throw(timeout))

    with pytest.raises(StageFailure) as exc_info:
        _runner(owned_root).validate(corpus, dictionary, work)

    failure = exc_info.value
    assert (failure.stage, failure.reason_code) == ("mfa", "command_timeout")
    assert (work / "validate.stdout.log").read_text(encoding="utf-8") == "partial stdout �"
    assert (work / "validate.stderr.log").read_text(encoding="utf-8") == "partial stderr �"


def test_work_directory_must_be_strict_owned_descendant_before_mkdir(tmp_path: Path) -> None:
    corpus, dictionary, _output, _work, owned_root = _inputs(tmp_path)
    nested_corpus = owned_root / "nested-corpus"
    work = nested_corpus / "work"

    with pytest.raises(StageFailure) as exc_info:
        _runner(owned_root).validate(nested_corpus, dictionary, work)

    assert (exc_info.value.stage, exc_info.value.reason_code) == (
        "mfa",
        "path_ownership_invalid",
    )
    assert not work.exists()


def test_validate_rejects_symlinked_validate_temp_before_starting_mfa(
    tmp_path: Path, monkeypatch
) -> None:
    corpus, dictionary, _output, work, owned_root = _inputs(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("untouched\n", encoding="utf-8")
    work.mkdir()
    (work / "validate_temp").symlink_to(outside, target_is_directory=True)
    argv_log = tmp_path / "argv.jsonl"
    monkeypatch.setenv("FAKE_MFA_ARGV_LOG", str(argv_log))

    with pytest.raises(StageFailure) as exc_info:
        _runner(owned_root).validate(corpus, dictionary, work)

    assert (exc_info.value.stage, exc_info.value.reason_code) == (
        "mfa",
        "path_ownership_invalid",
    )
    assert sentinel.read_text(encoding="utf-8") == "untouched\n"
    assert not argv_log.exists()


@pytest.mark.parametrize("unsafe_root", [Path("/"), Path.home()])
def test_owned_root_rejects_broad_protected_roots(tmp_path: Path, unsafe_root: Path) -> None:
    with pytest.raises(StageFailure) as exc_info:
        MfaRunner((sys.executable, str(FAKE_MFA)), owned_root=unsafe_root)

    assert (exc_info.value.stage, exc_info.value.reason_code) == (
        "mfa",
        "path_ownership_invalid",
    )


def test_owned_root_rejects_repository_root(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[2]

    with pytest.raises(StageFailure) as exc_info:
        MfaRunner((sys.executable, str(FAKE_MFA)), owned_root=repository_root)

    assert (exc_info.value.stage, exc_info.value.reason_code) == (
        "mfa",
        "path_ownership_invalid",
    )


def test_align_rejects_output_outside_owned_root_before_mkdir(tmp_path: Path) -> None:
    corpus, dictionary, _output, work, owned_root = _inputs(tmp_path)
    output = tmp_path / "outside-output"

    with pytest.raises(StageFailure) as exc_info:
        _runner(owned_root).align(corpus, dictionary, output, work)

    assert (exc_info.value.stage, exc_info.value.reason_code) == (
        "mfa",
        "path_ownership_invalid",
    )
    assert not output.exists()
    assert not work.exists()


def test_align_rejects_work_output_overlap_before_mkdir(tmp_path: Path) -> None:
    corpus, dictionary, _output, work, owned_root = _inputs(tmp_path)
    output = work / "output"

    with pytest.raises(StageFailure) as exc_info:
        _runner(owned_root).align(corpus, dictionary, output, work)

    assert (exc_info.value.stage, exc_info.value.reason_code) == (
        "mfa",
        "path_ownership_invalid",
    )
    assert not output.exists()
    assert not work.exists()
