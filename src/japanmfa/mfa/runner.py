"""Safe subprocess runner for Japanese MFA validation and alignment."""

from __future__ import annotations

import os
import subprocess
import math
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
        owned_root: Path,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
        dither: float = 1.0,
    ) -> None:
        if isinstance(command, (str, bytes)) or not command or not all(
            isinstance(part, str) and part for part in command
        ):
            raise ValueError("command must be a non-empty argument array")
        if not model:
            raise ValueError("model must be a non-empty string")
        if timeout is not None and timeout <= 0:
            raise ValueError("timeout must be positive")
        if isinstance(dither, bool) or not isinstance(dither, (int, float)) or not math.isfinite(float(dither)) or dither < 0:
            raise ValueError("dither must be finite and non-negative")
        self._owned_root = self._validate_owned_root(owned_root)
        self._command = tuple(command)
        self._model = model
        self._timeout = timeout
        self._env = None if env is None else {**os.environ, **dict(env)}
        self._dither = float(dither)

    def _build_validate_command(self, corpus_dir: Path, dictionary: Path, work_dir: Path) -> list[str]:
        """Build the version-sensitive MFA 3.x validation invocation."""
        return [
            *self._command,
            "validate",
            str(corpus_dir),
            str(dictionary),
            self._model,
            "--ignore_acoustics",
            "--output_directory",
            str(work_dir),
            "--temporary_directory",
            str(work_dir / "validate_temp"),
            "--clean",
        ]

    def _build_align_command(
        self, corpus_dir: Path, dictionary: Path, output_dir: Path, work_dir: Path,
        *, num_jobs: int | None = None,
    ) -> list[str]:
        """Build the version-sensitive MFA 3.x alignment invocation."""
        command = [
            *self._command,
            "align",
            str(corpus_dir),
            str(dictionary),
            self._model,
            str(output_dir),
            "--temporary_directory",
            str(work_dir),
            "--clean",
            "--no_tokenization",
            "--dither",
            format(self._dither, ".1f"),
        ]
        if num_jobs is not None:
            if isinstance(num_jobs, bool) or not isinstance(num_jobs, int) or num_jobs <= 0:
                raise ValueError("num_jobs must be a positive integer")
            command.extend(("--num_jobs", str(num_jobs)))
        return command

    def validate(self, corpus_dir: Path, dictionary: Path, work_dir: Path) -> None:
        """Validate one locked MFA corpus and preserve command logs."""
        corpus_dir = Path(corpus_dir)
        dictionary = Path(dictionary)
        work_dir = self._prepare_work_dir(work_dir, corpus_dir)
        self._prepare_validate_temp_dir(work_dir)
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
        self._validate_paths(corpus_dir, work_dir, output_dir)
        work_dir = self._create_work_dir(work_dir)
        self._prepare_validate_temp_dir(work_dir)
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

    def align_many(
        self, corpus_dir: Path, dictionary: Path, output_dir: Path, work_dir: Path,
        *, expected_stems: set[str], external_validate: bool = True,
        num_jobs: int | None = None, allow_partial: bool = False,
    ) -> dict[str, Path]:
        """Align named inputs; trusted batches may report missing grids per item."""
        if not expected_stems or any(not stem or Path(stem).name != stem for stem in expected_stems):
            raise ValueError("expected_stems must contain plain non-empty names")
        corpus_dir = Path(corpus_dir)
        dictionary = Path(dictionary)
        output_dir = Path(output_dir)
        self._validate_paths(corpus_dir, work_dir, output_dir)
        work_dir = self._create_work_dir(work_dir)
        if external_validate:
            self._prepare_validate_temp_dir(work_dir)
            self._run(self._build_validate_command(corpus_dir, dictionary, work_dir), work_dir, "validate")
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise _failure("output_directory_failed", f"could not create MFA output directory: {output_dir}",
                           output_dir=str(output_dir), error=str(exc)) from exc
        self._run(self._build_align_command(corpus_dir, dictionary, output_dir, work_dir,
                                            num_jobs=num_jobs), work_dir, "align")
        grids = {path.stem: path for path in output_dir.rglob("*")
                 if path.is_file() and path.suffix.casefold() == ".textgrid"}
        if set(grids) - expected_stems or (not allow_partial and set(grids) != expected_stems):
            raise _failure("output_coverage_mismatch", "MFA output grids do not match corpus inputs",
                           expected=sorted(expected_stems), actual=sorted(grids))
        return grids

    @staticmethod
    def _validate_owned_root(owned_root: Path) -> Path:
        path = Path(owned_root)
        if not path.is_absolute():
            raise _failure(
                "path_ownership_invalid",
                "MFA owned_root must be an absolute path",
                owned_root=str(path),
            )
        resolved = path.resolve()
        protected = {
            Path("/").resolve(),
            Path.home().resolve(),
            Path.home().resolve().parent,
            Path("/tmp").resolve(),
            Path("/var").resolve(),
            Path("/usr").resolve(),
            Path("/opt").resolve(),
            Path("/workspace").resolve(),
            Path("/workspaces").resolve(),
            Path(__file__).resolve().parents[3],
            Path.cwd().resolve(),
        }
        if resolved in protected:
            raise _failure(
                "path_ownership_invalid",
                "MFA owned_root is a protected broad path",
                owned_root=str(path),
            )
        return resolved

    @staticmethod
    def _overlaps(first: Path, second: Path) -> bool:
        return first == second or first in second.parents or second in first.parents

    def _validate_paths(
        self, corpus_dir: Path, work_dir: Path, output_dir: Path | None = None
    ) -> tuple[Path, Path, Path | None]:
        owned_root = self._owned_root
        corpus = Path(corpus_dir).resolve()
        work = Path(work_dir).resolve()
        output = None if output_dir is None else Path(output_dir).resolve()

        def strict_descendant(path: Path) -> bool:
            return path != owned_root and owned_root in path.parents

        if not strict_descendant(work):
            raise _failure(
                "path_ownership_invalid",
                "MFA work_dir must be a strict descendant of owned_root",
                owned_root=str(owned_root),
                work_dir=str(work),
            )
        if output is not None and not strict_descendant(output):
            raise _failure(
                "path_ownership_invalid",
                "MFA output_dir must be a strict descendant of owned_root",
                owned_root=str(owned_root),
                output_dir=str(output),
            )
        if output is not None and self._overlaps(work, output):
            raise _failure(
                "path_ownership_invalid",
                "MFA work_dir and output_dir must not overlap",
                work_dir=str(work),
                output_dir=str(output),
            )
        if self._overlaps(work, corpus) or (output is not None and self._overlaps(output, corpus)):
            raise _failure(
                "path_ownership_invalid",
                "MFA work/output paths must not overlap corpus_dir",
                corpus_dir=str(corpus),
                work_dir=str(work),
                output_dir=None if output is None else str(output),
            )
        return corpus, work, output

    def _prepare_work_dir(
        self, work_dir: Path, corpus_dir: Path, output_dir: Path | None = None
    ) -> Path:
        _corpus, work, _output = self._validate_paths(corpus_dir, work_dir, output_dir)
        return self._create_work_dir(work)

    def _prepare_validate_temp_dir(self, work_dir: Path) -> Path:
        """Prepare the validate-only temporary directory within the owned work tree."""
        temporary = Path(work_dir) / "validate_temp"
        if self._owned_root not in temporary.parents:
            raise _failure(
                "path_ownership_invalid",
                "MFA validation temporary directory must be a strict descendant of owned_root",
                owned_root=str(self._owned_root),
                temporary_directory=str(temporary),
            )

        current = temporary
        while current != self._owned_root:
            if current.is_symlink():
                raise _failure(
                    "path_ownership_invalid",
                    "MFA validation temporary path cannot contain symlink components",
                    owned_root=str(self._owned_root),
                    temporary_directory=str(temporary),
                    symlink=str(current),
                )
            current = current.parent

        try:
            resolved = temporary.resolve()
        except OSError as exc:
            raise _failure(
                "path_ownership_invalid",
                "could not resolve MFA validation temporary directory",
                owned_root=str(self._owned_root),
                temporary_directory=str(temporary),
                error=str(exc),
            ) from exc
        if resolved != temporary or self._owned_root not in resolved.parents:
            raise _failure(
                "path_ownership_invalid",
                "MFA validation temporary directory escapes owned_root",
                owned_root=str(self._owned_root),
                temporary_directory=str(temporary),
                resolved_directory=str(resolved),
            )

        try:
            if temporary.exists() and not temporary.is_dir():
                raise OSError("path is not a directory")
            temporary.mkdir(parents=False, exist_ok=True)
        except OSError as exc:
            raise _failure(
                "work_directory_failed",
                f"could not create MFA validation temporary directory: {temporary}",
                temporary_directory=str(temporary),
                error=str(exc),
            ) from exc
        return temporary

    @staticmethod
    def _create_work_dir(work_dir: Path) -> Path:
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
            stdout = self._decode_stream(exc.stdout)
            stderr = self._decode_stream(exc.stderr)
            self._write_logs(stdout_log, stderr_log, stdout, stderr)
            raise _failure(
                "command_timeout",
                f"MFA {name} command timed out",
                command=command,
                timeout=self._timeout,
                stdout=stdout[-4000:],
                stderr=stderr[-4000:],
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
    def _decode_stream(value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        if isinstance(value, str):
            return value
        return str(value)

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
