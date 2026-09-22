"""Strict subprocess adapter for the Japanese MFA G2P command."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Mapping, Sequence

from japanmfa.domain import Pronunciation
from japanmfa.errors import StageFailure


_KATAKANA_RE = re.compile(r"[ァ-ヿー]+")


def _failure(reason_code: str, message: str, **details: object) -> StageFailure:
    return StageFailure("mfa_g2p", reason_code, message, details)


class MfaG2pClient:
    """Invoke MFA G2P and return exactly one pronunciation per input position."""

    def __init__(
        self,
        command: Sequence[str],
        model: str = "japanese_mfa",
        *,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        if isinstance(command, (str, bytes)) or not command or not all(
            isinstance(part, str) and part for part in command
        ):
            raise ValueError("command must be a non-empty argument array")
        if not model:
            raise ValueError("model must be a non-empty string")
        if timeout is not None and timeout <= 0:
            raise ValueError("timeout must be positive")
        self._command = tuple(command)
        self._model = model
        self._timeout = timeout
        self._env = None if env is None else {**os.environ, **dict(env)}

    def _build_command(self, input_path: Path, output_path: Path) -> list[str]:
        """Build the version-sensitive MFA invocation in one compatibility seam."""
        return [
            *self._command,
            "g2p",
            str(input_path),
            self._model,
            str(output_path),
        ]

    def pronounce(
        self, readings: Sequence[str], work_dir: Path
    ) -> tuple[Pronunciation, ...]:
        """Run G2P for *readings*, preserving duplicate input positions."""
        requested = tuple(readings)
        for index, reading in enumerate(requested):
            if not isinstance(reading, str) or not reading:
                raise _failure(
                    "invalid_reading",
                    "MFA G2P readings must be non-empty strings",
                    index=index,
                )
            if not _KATAKANA_RE.fullmatch(reading):
                raise _failure(
                    "invalid_reading",
                    f"MFA G2P reading is not locked Katakana: {reading!r}",
                    index=index,
                    reading=reading,
                )

        if not requested:
            return ()

        work_dir = Path(work_dir)
        try:
            work_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise _failure(
                "work_directory_failed",
                f"could not create MFA G2P work directory: {work_dir}",
                work_dir=str(work_dir),
                error=str(exc),
            ) from exc

        input_path = work_dir / "g2p_input.txt"
        output_path = work_dir / "g2p_output.dict"
        try:
            input_path.write_text("".join(f"{reading}\n" for reading in requested), encoding="utf-8")
        except OSError as exc:
            raise _failure(
                "input_write_failed",
                f"could not write MFA G2P input: {input_path}",
                input_path=str(input_path),
                error=str(exc),
            ) from exc

        command = self._build_command(input_path, output_path)
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                shell=False,
                timeout=self._timeout,
                env=self._env,
            )
        except subprocess.TimeoutExpired as exc:
            raise _failure(
                "command_timeout",
                "MFA G2P command timed out",
                command=command,
                timeout=self._timeout,
            ) from exc
        except OSError as exc:
            raise _failure(
                "command_start_failed",
                f"could not start MFA G2P command: {exc}",
                command=command,
            ) from exc

        if completed.returncode != 0:
            raise _failure(
                "command_failed",
                f"MFA G2P command exited with status {completed.returncode}",
                command=command,
                returncode=completed.returncode,
                stderr=completed.stderr[-4000:],
            )

        try:
            output = output_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise _failure(
                "output_read_failed",
                f"could not read MFA G2P output: {output_path}",
                output_path=str(output_path),
                error=str(exc),
            ) from exc

        by_reading: dict[str, Pronunciation] = {}
        for line_number, raw_line in enumerate(output.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            columns = line.split(None, 1)
            if len(columns) != 2 or not columns[1].strip():
                raise _failure(
                    "malformed_output",
                    "MFA G2P dictionary rows require a reading and phones",
                    line_number=line_number,
                    line=raw_line,
                )
            reading, phone_text = columns
            pronunciation = Pronunciation(reading, tuple(phone_text.split()))
            if reading in by_reading:
                raise _failure(
                    "multiple_pronunciations",
                    f"MFA G2P returned multiple pronunciations for {reading!r}",
                    reading=reading,
                )
            by_reading[reading] = pronunciation

        requested_set = set(requested)
        unexpected = sorted(set(by_reading) - requested_set)
        if unexpected:
            raise _failure(
                "out_of_vocabulary",
                "MFA G2P returned readings that were not requested",
                readings=unexpected,
            )
        missing = sorted(requested_set - set(by_reading))
        if missing:
            raise _failure(
                "missing_pronunciation",
                "MFA G2P did not return every requested reading",
                readings=missing,
            )

        return tuple(by_reading[reading] for reading in requested)
