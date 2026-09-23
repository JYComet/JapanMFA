"""Batched line-oriented adapter for isolated tdmelodic ``sy2a`` calls."""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from typing import Mapping, Sequence

from japanmfa.errors import StageFailure


def resolve_tdmelodic_command(raw: str | None = None) -> tuple[str, ...]:
    """Resolve the shared argv configuration used by run and preflight."""
    configured = os.environ.get("JAPANMFA_TDMELODIC_COMMAND", "tdmelodic") if raw is None else raw
    try:
        command = tuple(shlex.split(configured))
    except ValueError as exc:
        raise ValueError("tdmelodic command configuration is malformed") from exc
    if not command:
        raise ValueError("tdmelodic command configuration is empty")
    return command


@dataclass(frozen=True)
class AccentRequest:
    token_index: int
    surface: str
    yomi: str


class TdmelodicClient:
    """Run one isolated tdmelodic process for a batch of token requests."""

    def __init__(
        self,
        command: Sequence[str],
        *,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        if isinstance(command, (str, bytes)) or not command or not all(
            isinstance(part, str) and part for part in command
        ):
            raise ValueError("command must be a non-empty argument array")
        if timeout is not None and timeout <= 0:
            raise ValueError("timeout must be positive")
        self._command = tuple(command)
        self._timeout = timeout
        self._env = None if env is None else {**os.environ, **dict(env)}

    def predict(self, requests: Sequence[AccentRequest]) -> dict[int, str]:
        """Call ``sy2a(surface,yomi)`` once per request and validate coverage."""
        batch = list(requests)
        if not batch:
            return {}

        seen_indices: set[int] = set()
        lines: list[str] = []
        for request in batch:
            if not isinstance(request, AccentRequest):
                raise StageFailure(
                    "accent",
                    "invalid_request",
                    "tdmelodic requests must be AccentRequest records",
                    {},
                )
            if request.token_index in seen_indices:
                raise StageFailure(
                    "accent",
                    "invalid_request",
                    "tdmelodic request contains duplicate token indices",
                    {"token_index": request.token_index},
                )
            seen_indices.add(request.token_index)
            if not request.surface or not request.yomi:
                raise StageFailure(
                    "accent",
                    "invalid_request",
                    "tdmelodic surface and yomi must be non-empty",
                    {"token_index": request.token_index},
                )
            if any(delimiter in request.surface for delimiter in ",\r\n"):
                raise StageFailure(
                    "accent",
                    "invalid_request",
                    "tdmelodic surface cannot contain commas or newlines",
                    {"token_index": request.token_index},
                )
            if any(delimiter in request.yomi for delimiter in ",\r\n"):
                raise StageFailure(
                    "accent",
                    "invalid_request",
                    "tdmelodic yomi cannot contain commas or newlines",
                    {"token_index": request.token_index},
                )
            lines.append(f"{request.surface},{request.yomi}")

        try:
            completed = subprocess.run(
                self._command,
                input="\n".join(lines) + "\n",
                capture_output=True,
                text=True,
                check=False,
                shell=False,
                timeout=self._timeout,
                env=self._env,
            )
        except subprocess.TimeoutExpired as exc:
            raise StageFailure(
                "accent",
                "command_timeout",
                "tdmelodic command timed out",
                {"command": list(self._command), "timeout": self._timeout},
            ) from exc
        except OSError as exc:
            raise StageFailure(
                "accent",
                "command_start_failed",
                f"could not start tdmelodic command: {exc}",
                {"command": list(self._command)},
            ) from exc

        if completed.returncode != 0:
            raise StageFailure(
                "accent",
                "command_failed",
                f"tdmelodic command exited with status {completed.returncode}",
                {
                    "returncode": completed.returncode,
                    "stderr": completed.stderr[-4000:],
                },
            )

        raw_lines = completed.stdout.splitlines()
        if len(raw_lines) != len(batch):
            raise StageFailure(
                "accent",
                "output_count_mismatch",
                "tdmelodic must return exactly one output line per request",
                {"expected": len(batch), "actual": len(raw_lines)},
            )
        outputs: list[str] = []
        for line_number, line in enumerate(raw_lines):
            output = line.strip()
            if not output:
                raise StageFailure(
                    "accent",
                    "empty_output",
                    "tdmelodic returned an empty output line",
                    {"line": line_number},
                )
            outputs.append(output)

        return {request.token_index: output for request, output in zip(batch, outputs)}
