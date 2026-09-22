"""Typer command line entry points for JapanMFA."""

from __future__ import annotations

import json
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from typing import Annotated, Any

import typer

from .config import PipelineConfig
from .errors import StageFailure
from .pipeline import JapanMFAPipeline


app = typer.Typer(help="Japanese-only MFA five-track forced alignment")


def _validate_roots(input_root: Path, output_root: Path) -> tuple[Path, Path]:
    source = input_root.resolve()
    destination = output_root.resolve()
    if source == destination or source in destination.parents:
        raise ValueError("output root must not be identical to or nested inside input root")
    return source, destination


def _build_pipeline(config_path: Path) -> JapanMFAPipeline:
    return JapanMFAPipeline(PipelineConfig.load(config_path.resolve()))


def _run(
    input_root: Path,
    output_root: Path,
    config_path: Path,
    overrides: Path | None,
    limit: int | None = None,
) -> int:
    source, destination = _validate_roots(input_root, output_root)
    if limit is not None and limit <= 0:
        raise ValueError("limit must be a positive integer")
    pipeline = _build_pipeline(config_path)
    resolved_overrides = None if overrides is None else overrides.resolve()
    if limit is None:
        result = pipeline.run(source, destination, resolved_overrides)
    else:
        result = pipeline.run(source, destination, resolved_overrides, limit=limit)
    typer.echo(f"summary: {result.summary_path}")
    typer.echo(json.dumps(result.summary, ensure_ascii=False, sort_keys=True))
    return 0


@app.command("run")
def run(
    input_root: Annotated[Path, typer.Option("--input", exists=True, file_okay=False, dir_okay=True)],
    output_root: Annotated[Path, typer.Option("--output", file_okay=False, dir_okay=True)],
    config: Annotated[Path, typer.Option("--config", exists=True, dir_okay=False)] = Path("configs/default.yaml"),
    overrides: Annotated[Path | None, typer.Option("--overrides", exists=True, dir_okay=False)] = None,
    limit: Annotated[int | None, typer.Option("--limit", min=1)] = None,
) -> None:
    """Align every WAV discovered under INPUT."""
    try:
        _run(input_root, output_root, config, overrides, limit)
    except StageFailure as exc:
        typer.echo(f"batch setup failure: {exc.reason_code}: {exc.message}", err=True)
        raise typer.Exit(code=1)
    except (OSError, ValueError, RuntimeError) as exc:
        typer.echo(f"setup failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command("run-file")
def run_file(
    audio: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    text: Annotated[Path | None, typer.Option("--text", exists=True, dir_okay=False)] = None,
    output_root: Annotated[Path, typer.Option("--output", file_okay=False, dir_okay=True)] = Path("output"),
    config: Annotated[Path, typer.Option("--config", exists=True, dir_okay=False)] = Path("configs/default.yaml"),
    overrides: Annotated[Path | None, typer.Option("--overrides", exists=True, dir_okay=False)] = None,
) -> None:
    """Align one WAV using a temporary one-item corpus manifest."""
    try:
        if not audio.is_file() or audio.is_dir():
            raise ValueError(f"audio must be a regular file: {audio}")
        real_audio = audio.resolve()
        if not real_audio.is_file() or real_audio.is_dir():
            raise ValueError(f"audio target must be a regular file: {audio}")
        original_parent = real_audio.parent
        resolved_output = output_root.resolve()
        if resolved_output == original_parent or original_parent in resolved_output.parents:
            raise ValueError("output root must not be identical to or nested inside the input corpus")
        with tempfile.TemporaryDirectory(prefix="japanmfa-run-file-") as temporary:
            root = Path(temporary)
            copied_audio = root / audio.name
            shutil.copy2(audio, copied_audio)
            if text is not None:
                shutil.copy2(text, copied_audio.with_suffix(".txt"))
            _run(root, output_root, config, overrides)
    except StageFailure as exc:
        typer.echo(f"batch setup failure: {exc.reason_code}: {exc.message}", err=True)
        raise typer.Exit(code=1)
    except (OSError, ValueError, RuntimeError) as exc:
        typer.echo(f"setup failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command("inspect")
def inspect(manifest: Annotated[Path, typer.Argument(exists=True, dir_okay=False)]) -> None:
    """Print aligned/skipped/failed counts from a manifest without modifying it."""
    counts = Counter({"aligned": 0, "skipped": 0, "failed": 0})
    try:
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            status = row.get("status")
            if status not in counts:
                raise ValueError(f"unknown manifest status: {status!r}")
            counts[status] += 1
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        typer.echo(f"inspect failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    for status in ("aligned", "skipped", "failed"):
        typer.echo(f"{status}: {counts[status]}")


@app.command("check")
def check(
    config: Annotated[Path, typer.Option("--config", exists=True, dir_okay=False)] = Path("configs/default.yaml"),
) -> None:
    """Run Task 11's environment/model preflight checks."""
    try:
        from .checks import run_preflight
    except ImportError as exc:
        typer.echo(f"check unavailable: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    try:
        report: Any = run_preflight(PipelineConfig.load(config.resolve()))
    except Exception as exc:
        typer.echo(f"check failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if hasattr(report, "to_json"):
        typer.echo(report.to_json())
    else:
        typer.echo(json.dumps(report, ensure_ascii=False, sort_keys=True, default=str))
    if (isinstance(report, dict) and report.get("ok") is False) or getattr(report, "ok", True) is False:
        raise typer.Exit(code=1)


if __name__ == "__main__":  # pragma: no cover
    app()


__all__ = ["app"]
