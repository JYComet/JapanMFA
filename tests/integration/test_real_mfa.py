from __future__ import annotations

import math
import os
import shlex
import wave
from pathlib import Path

import pytest

from japanmfa.mfa.g2p import MfaG2pClient
from japanmfa.mfa.runner import MfaRunner
from japanmfa.mfa.textgrid import parse_mfa_textgrid


pytestmark = pytest.mark.real_models


def _mfa_command() -> tuple[str, ...]:
    raw = os.environ.get("JAPANMFA_REAL_MFA_COMMAND")
    if raw:
        command = tuple(shlex.split(raw))
        if command:
            return command
    runtime = os.environ.get("JAPANMFA_REAL_MFA_RUNTIME")
    if not runtime:
        pytest.skip(
            "set JAPANMFA_REAL_MFA_COMMAND or JAPANMFA_REAL_MFA_RUNTIME "
            "to opt into the real MFA test"
        )
    executable = Path(runtime).expanduser()
    if executable.is_dir():
        executable /= "bin/mfa"
    if not executable.is_file():
        pytest.skip(f"MFA runtime does not point to an executable: {executable}")
    return (str(executable),)


def _runtime_env() -> dict[str, str] | None:
    root = os.environ.get("MFA_ROOT_DIR") or os.environ.get("JAPANMFA_REAL_MFA_ROOT")
    return None if root is None else {"MFA_ROOT_DIR": root}


def _write_bounded_wav(path: Path) -> None:
    sample_rate = 16_000
    frames = bytearray()
    for index in range(sample_rate):
        amplitude = int(8_000 * math.sin(2 * math.pi * 220 * index / sample_rate))
        frames.extend(amplitude.to_bytes(2, byteorder="little", signed=True))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(frames)


def test_real_mfa_g2p_and_alignment_emit_locked_alias_tiers(tmp_path: Path) -> None:
    g2p_model = os.environ.get("JAPANMFA_REAL_MFA_G2P_MODEL")
    acoustic_model = os.environ.get("JAPANMFA_REAL_MFA_ACOUSTIC_MODEL")
    if not g2p_model or not acoustic_model:
        pytest.skip(
            "set JAPANMFA_REAL_MFA_G2P_MODEL and "
            "JAPANMFA_REAL_MFA_ACOUSTIC_MODEL to opt into the real MFA test"
        )

    command = _mfa_command()
    env = _runtime_env()
    g2p = MfaG2pClient(command, model=g2p_model, env=env)
    pronunciation = g2p.pronounce(("ネコ",), tmp_path / "g2p")[0]

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    _write_bounded_wav(corpus / "sample.wav")
    (corpus / "sample.lab").write_text("jmfa_000000\n", encoding="utf-8")
    dictionary = tmp_path / "sample.dict"
    dictionary.write_text(
        f"jmfa_000000 {' '.join(pronunciation.phones)}\n", encoding="utf-8"
    )

    owned_root = tmp_path / "mfa-root"
    grid = MfaRunner(command, model=acoustic_model, owned_root=owned_root, env=env).align(
        corpus, dictionary, owned_root / "aligned", owned_root / "work"
    )
    alignment = parse_mfa_textgrid(grid, frozenset({"", "sil", "sp", "spn"}))

    assert [word.alias for word in alignment.words] == ["jmfa_000000"]
    assert alignment.phones
    assert all(phone.word_alias == "jmfa_000000" for phone in alignment.phones)
