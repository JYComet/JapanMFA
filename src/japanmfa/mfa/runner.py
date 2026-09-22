"""Safe subprocess runner for Japanese MFA validation and alignment."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Mapping, Sequence

from japanmfa.errors import StageFailure


def _failure(reason_code: str, message: str, **details: object) -> StageFailure:
    return StageFailure("mfa", reason_code, message, details)


class MfaRunner:
    """Invoke the pinned MFA 3.x validate/align command pair."""

    def __init__(
        self,
        command: Sequence[str] = ("mfa",),
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

    def _build_validate_command(self, corpus_dir: Path, dictionary: Path, work_dir: Path) -> list[str]:
        """Build the version-sensitive MFA 3.x validation invocation."""
        return [
            *self._command,
            "validate",
            str(corpus_dir),
            str(dictionary),
            self._model,
            "--output_directory",
            str(work_dir),
        ]

    def _build_align_command(
        self, corpus_dir: Path, dictionary: Path, output_dir: Path, work_dir: Path
    ) -> list[str]:
        """Build the version-sensitive MFA 3.x alignment invocation."""
        return [
            *self._command,
            "align",
            str(corpus_dir),
            str(dictionary),
            self._model,
            str(output_dir),
            "--temporary_directory",
            str(work_dir),
            "--clean",
        ]

    def validate(self, corpus_dir: Path, dictionary: Path, work_dir: Path) -> None:
        """Validate one locked MFA corpus and preserve command logs."""
        corpus_dir = Path(corpus_dir)
        dictionary = Path(dictionary)
        work_dir = self._prepare_work_dir(work_dir, corpus_dir)
        self._run(
            self._build_validate_command(corpus_dir, dictionary, work_dir),
            work_dir,
            "validate",
        )

    def align(
        self, corpus_dir: Path, dictionary: Path, output_dir: Path, work_dir: Path
    ) -> Path:
        """Validate then align and return the sole produced TextGrid."""
        corpus_dir = Path(corpus_dir)
        dictionary = Path(dictionary)
        output_dir = Path(output_dir)
        work_dir = self._prepare_work_dir(work_dir, corpus_dir, output_dir)
        self._run(
            self._build_validate_command(corpus_dir, dictionary, work_dir),
            work_dir,
            "validate",
        )
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise _failure(
                "output_directory_failed",
                f"could not create MFA output directory: {output_dir}",
                output_dir=str(output_dir),
                error=str(exc),
            ) from exc
        self._run(
            self._build_align_command(corpus_dir, dictionary, output_dir, work_dir),
            work_dir,
            "align",
        )
        textgrids = sorted(
            (path for path in output_dir.rglob("*") if path.is_file() and path.suffix.casefold() == ".textgrid"),
            key=lambda path: path.relative_to(output_dir).as_posix(),
        )
        if not textgrids:
            raise _failure(
                "missing_output",
                f"MFA alignment produced no TextGrid in {output_dir}",
                output_dir=str(output_dir),
                stdout_log=str(work_dir / "align.stdout.log"),
                stderr_log=str(work_dir / "align.stderr.log"),
            )
        if len(textgrids) > 1:
            raise _failure(
                "multiple_outputs",
                f"MFA alignment produced multiple TextGrids in {output_dir}",
                output_dir=str(output_dir),
                outputs=[str(path) for path in textgrids],
            )
        return textgrids[0]

    def _prepare_work_dir(
        self, work_dir: Path, corpus_dir: Path, output_dir: Path | None = None
    ) -> Path:
        work_dir = Path(work_dir)
        if not work_dir.is_absolute():
            raise _failure(
                "work_directory_invalid",
                "MFA work directory must be an absolute generated path",
                work_dir=str(work_dir),
            )
        resolved = work_dir.resolve()
        forbidden = {
            Path("/").resolve(),
            Path.home().resolve(),
            Path.cwd().resolve(),
            Path(__file__).resolve().parents[3],
            Path(corpus_dir).resolve(),
        }
        if output_dir is not None:
            forbidden.add(Path(output_dir).resolve())
        corpus_resolved = Path(corpus_dir).resolve()
        is_parent_of_corpus = corpus_resolved != resolved and resolved in corpus_resolved.parents
        output_resolved = Path(output_dir).resolve() if output_dir is not None else None
        is_parent_of_output = (
            output_resolved is not None
            and output_resolved != resolved
            and resolved in output_resolved.parents
        )
        if resolved in forbidden or is_parent_of_corpus or is_parent_of_output:
            raise _failure(
                "work_directory_invalid",
                "MFA work directory must be utterance-owned and distinct from inputs",
                work_dir=str(work_dir),
            )
        try:
            if work_dir.exists() and not work_dir.is_dir():
                raise OSError("path is not a directory")
            work_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise _failure(
                "work_directory_failed",
                f"could not create MFA work directory: {work_dir}",
                work_dir=str(work_dir),
                error=str(exc),
            ) from exc
        return work_dir

    def _run(self, command: list[str], work_dir: Path, name: str) -> None:
        stdout_log = work_dir / f"{name}.stdout.log"
        stderr_log = work_dir / f"{name}.stderr.log"
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
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            self._write_logs(stdout_log, stderr_log, stdout, stderr)
            raise _failure(
                "command_timeout",
                f"MFA {name} command timed out",
                command=command,
                timeout=self._timeout,
                stdout_log=str(stdout_log),
                stderr_log=str(stderr_log),
            ) from exc
        except OSError as exc:
            self._write_logs(stdout_log, stderr_log, "", str(exc))
            raise _failure(
                "command_start_failed",
                f"could not start MFA {name} command: {exc}",
                command=command,
                stdout_log=str(stdout_log),
                stderr_log=str(stderr_log),
            ) from exc

        self._write_logs(stdout_log, stderr_log, completed.stdout, completed.stderr)
        if completed.returncode != 0:
            raise _failure(
                "command_failed",
                f"MFA {name} command exited with status {completed.returncode}",
                command=command,
                returncode=completed.returncode,
                stdout=completed.stdout[-4000:],
                stderr=completed.stderr[-4000:],
                stdout_log=str(stdout_log),
                stderr_log=str(stderr_log),
            )

    @staticmethod
    def _write_logs(stdout_log: Path, stderr_log: Path, stdout: str, stderr: str) -> None:
        try:
            stdout_log.write_text(stdout, encoding="utf-8")
            stderr_log.write_text(stderr, encoding="utf-8")
        except OSError as exc:
            raise _failure(
                "log_write_failed",
                "could not preserve MFA command logs",
                stdout_log=str(stdout_log),
                stderr_log=str(stderr_log),
                error=str(exc),
            ) from exc


__all__ = ["MfaRunner"]
