from __future__ import annotations

import json
import os
import re
import shlex
from dataclasses import replace
from pathlib import Path

import pytest

from japanmfa.accent.tdmelodic import TdmelodicClient
from japanmfa.config import PipelineConfig
from japanmfa.domain import PhoneAnnotation, PhoneInterval
from japanmfa.output.textgrid import validate_five_tier_textgrid, write_five_tier_textgrid
from japanmfa.pipeline import JapanMFAPipeline


pytestmark = pytest.mark.real_models

_TERMINAL_STATUSES = frozenset({"aligned", "skipped", "failed"})


def test_real_artifact_validator_rejects_summary_mismatch(tmp_path: Path) -> None:
    (tmp_path / "manifest.jsonl").write_text(
        json.dumps({"status": "skipped", "utterance_id": "u1"}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "summary.json").write_text(
        json.dumps({"total": 0, "counts": {"aligned": 0, "failed": 0, "skipped": 0}}),
        encoding="utf-8",
    )

    with pytest.raises(AssertionError, match="summary.json total"):
        _validate_real_artifact(tmp_path, frozenset({""}))


def test_real_artifact_validator_rejects_nonterminal_manifest_status(tmp_path: Path) -> None:
    (tmp_path / "manifest.jsonl").write_text(
        json.dumps({"status": "running", "utterance_id": "u1"}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "summary.json").write_text(
        json.dumps({"total": 1, "counts": {"aligned": 0, "failed": 0, "skipped": 0}}),
        encoding="utf-8",
    )

    with pytest.raises(AssertionError, match="non-terminal status"):
        _validate_real_artifact(tmp_path, frozenset({""}))


def test_real_artifact_validator_checks_every_aligned_artifact(tmp_path: Path) -> None:
    first = tmp_path / "artifact-u1"
    second = tmp_path / "artifact-u2"
    _write_aligned_fixture(first, "u1", metadata_duration=1.0, grid_duration=1.0)
    _write_aligned_fixture(second, "u2", metadata_duration=2.0, grid_duration=1.0)
    (tmp_path / "manifest.jsonl").write_text(
        "\n".join(
            json.dumps(
                {"status": "aligned", "utterance_id": utterance_id, "artifact_dir": str(artifact)}
            )
            for utterance_id, artifact in (("u1", first), ("u2", second))
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "summary.json").write_text(
        json.dumps({"total": 2, "counts": {"aligned": 2, "failed": 0, "skipped": 0}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="header duration does not match requested duration"):
        _validate_real_artifact(tmp_path, frozenset({""}))


def test_real_pipeline_explicit_missing_output_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JAPANMFA_REAL_PIPELINE_OUTPUT", str(tmp_path / "missing-output"))
    monkeypatch.delenv("JAPANMFA_REAL_PIPELINE_CONFIG", raising=False)
    monkeypatch.delenv("JAPANMFA_REAL_PIPELINE_INPUT", raising=False)

    with pytest.raises(AssertionError, match="lacks manifest.jsonl"):
        test_real_pipeline_validates_aligned_five_tier_artifact(tmp_path, monkeypatch)


def test_real_artifact_validator_resolves_textgrid_from_metadata_for_nested_id(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact-u1"
    _write_aligned_fixture(artifact, "u1", metadata_duration=1.0, grid_duration=1.0)
    (tmp_path / "manifest.jsonl").write_text(
        json.dumps(
            {
                "status": "aligned",
                "utterance_id": "nested/u1",
                "artifact_dir": str(artifact),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "summary.json").write_text(
        json.dumps({"total": 1, "counts": {"aligned": 1, "failed": 0, "skipped": 0}}),
        encoding="utf-8",
    )

    _validate_real_artifact(tmp_path, frozenset({""}))


def _write_aligned_fixture(
    artifact: Path,
    utterance_id: str,
    *,
    metadata_duration: float,
    grid_duration: float,
) -> None:
    artifact.mkdir(parents=True)
    write_five_tier_textgrid(
        artifact / f"{utterance_id}.TextGrid",
        grid_duration,
        "原文",
        "ゲンブン",
        (
            PhoneAnnotation(
                PhoneInterval(0.0, grid_duration, "k"),
                token_index=0,
                morae=(),
                kana_label="ゲ",
                tone_label="LL",
                is_silence=False,
            ),
        ),
    )
    (artifact / "alignment.json").write_text(
        json.dumps(
            {
                "duration": metadata_duration,
                "textgrid": str((artifact / f"{utterance_id}.TextGrid").resolve()),
            }
        ),
        encoding="utf-8",
    )
    (artifact / ".japanmfa.complete").write_text(
        json.dumps(
            {
                "textgrid": str((artifact / f"{utterance_id}.TextGrid").resolve()),
                "alignment": str((artifact / "alignment.json").resolve()),
            }
        ),
        encoding="utf-8",
    )
    for required_name in ("asr.json", "frontend.json", "mora.json", "mfa.json"):
        (artifact / required_name).write_text("{}\n", encoding="utf-8")
    (artifact / "mfa").mkdir()


def _command(command_name: str, runtime_name: str) -> tuple[str, ...]:
    raw = os.environ.get(command_name)
    if raw:
        command = tuple(shlex.split(raw))
        if command:
            return command
    runtime = os.environ.get(runtime_name)
    if not runtime:
        pytest.skip(f"set {command_name} or {runtime_name} to opt into the real pipeline test")
    executable = Path(runtime).expanduser()
    if executable.is_dir():
        executable /= "bin/mfa" if "MFA" in runtime_name else "bin/python"
    if not executable.is_file():
        pytest.skip(f"runtime does not point to an executable: {executable}")
    if "MFA" in runtime_name:
        return (str(executable),)
    return (str(executable), "-m", "japanmfa.asr.worker")


def _tier_boundaries(path: Path, tier_name: str) -> tuple[tuple[float, float], ...]:
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r"(?=^    item \[\d+\]:$)", text, flags=re.MULTILINE)
    block = next((item for item in blocks if f'name = "{tier_name}"' in item), None)
    assert block is not None, f"missing tier {tier_name!r}"
    return tuple(
        (float(start), float(end))
        for start, end in re.findall(
            r"intervals \[\d+\]:\s*xmin\s*=\s*([^\n]+)\s*xmax\s*=\s*([^\n]+)",
            block,
        )
    )


def _validate_real_artifact(root: Path, silence_labels: frozenset[str]) -> None:
    manifest = root / "manifest.jsonl"
    rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line]
    statuses = []
    for index, row in enumerate(rows):
        assert isinstance(row, dict), f"manifest row {index} is not a JSON object"
        status = row.get("status")
        assert status in _TERMINAL_STATUSES, (
            f"manifest row {index} has non-terminal status: {status!r}"
        )
        statuses.append(status)
    counts = {status: statuses.count(status) for status in sorted(_TERMINAL_STATUSES)}
    summary_path = root / "summary.json"
    assert summary_path.is_file(), f"missing summary.json: {summary_path}"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary.get("total") == len(rows), (
        f"summary.json total {summary.get('total')!r} does not match "
        f"manifest row count {len(rows)}"
    )
    assert summary.get("counts") == counts, (
        f"summary.json counts {summary.get('counts')!r} do not match manifest counts {counts!r}"
    )
    aligned = [row for row in rows if row.get("status") == "aligned"]
    assert aligned, "real pipeline produced no aligned outcome"
    root_resolved = root.resolve()
    for index, row in enumerate(aligned):
        artifact_value = row.get("artifact_dir")
        assert isinstance(artifact_value, str) and artifact_value, (
            f"aligned manifest row {index} has no artifact_dir"
        )
        artifact = Path(artifact_value)
        if not artifact.is_absolute():
            artifact = root / artifact
        artifact = artifact.resolve()
        try:
            artifact.relative_to(root_resolved)
        except ValueError as exc:
            raise AssertionError(f"aligned manifest row {index} artifact escapes output root") from exc

        metadata_path = artifact / "alignment.json"
        marker_path = artifact / ".japanmfa.complete"
        assert marker_path.is_file(), (
            f"aligned manifest row {index} lacks completion marker"
        )
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        for required_name in ("asr.json", "frontend.json", "mora.json", "mfa.json"):
            required_path = artifact / required_name
            assert required_path.is_file(), (
                f"aligned manifest row {index} lacks {required_name}"
            )
            assert isinstance(
                json.loads(required_path.read_text(encoding="utf-8")), dict
            )
        assert (artifact / "mfa").is_dir(), (
            f"aligned manifest row {index} lacks MFA diagnostic directory"
        )
        textgrid_value = metadata.get("textgrid")
        assert isinstance(textgrid_value, str) and textgrid_value, (
            f"aligned manifest row {index} alignment.json has no textgrid path"
        )
        grid = Path(textgrid_value)
        if not grid.is_absolute():
            grid = artifact / grid
        grid = grid.resolve()
        try:
            grid.relative_to(artifact)
        except ValueError as exc:
            raise AssertionError(f"aligned manifest row {index} textgrid escapes artifact") from exc

        assert Path(str(marker.get("textgrid"))).resolve() == grid
        assert Path(str(marker.get("alignment"))).resolve() == metadata_path.resolve()

        validate_five_tier_textgrid(grid, float(metadata["duration"]), silence_labels)
        phone_boundaries = _tier_boundaries(grid, "phones")
        phone_kana_boundaries = _tier_boundaries(grid, "phone_kana")
        phone_tone_boundaries = _tier_boundaries(grid, "phone_tone")
        assert phone_boundaries == phone_kana_boundaries == phone_tone_boundaries


def test_real_pipeline_validates_aligned_five_tier_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sample_output = os.environ.get("JAPANMFA_REAL_PIPELINE_OUTPUT")
    if sample_output:
        root = Path(sample_output).expanduser()
        assert (root / "manifest.jsonl").is_file(), (
            f"JAPANMFA_REAL_PIPELINE_OUTPUT lacks manifest.jsonl: {root}"
        )
        _validate_real_artifact(root, frozenset({"", "sil", "sp", "spn"}))
        return

    config_path = os.environ.get("JAPANMFA_REAL_PIPELINE_CONFIG")
    input_root = os.environ.get("JAPANMFA_REAL_PIPELINE_INPUT")
    if not config_path or not input_root:
        pytest.skip(
            "set JAPANMFA_REAL_PIPELINE_CONFIG and JAPANMFA_REAL_PIPELINE_INPUT "
            "(or JAPANMFA_REAL_PIPELINE_OUTPUT) to opt into the real pipeline test"
        )
    config = PipelineConfig.load(Path(config_path).expanduser())
    source = Path(input_root).expanduser()
    if not source.is_dir():
        pytest.skip(f"JAPANMFA_REAL_PIPELINE_INPUT is not a directory: {source}")
    qwen_model = os.environ.get("JAPANMFA_REAL_QWEN_MODEL")
    mfa_acoustic_model = os.environ.get("JAPANMFA_REAL_MFA_ACOUSTIC_MODEL")
    mfa_g2p_model = os.environ.get("JAPANMFA_REAL_MFA_G2P_MODEL")
    if not qwen_model or not mfa_acoustic_model or not mfa_g2p_model:
        pytest.skip(
            "set JAPANMFA_REAL_QWEN_MODEL, "
            "JAPANMFA_REAL_MFA_ACOUSTIC_MODEL, and "
            "JAPANMFA_REAL_MFA_G2P_MODEL for the real pipeline"
        )
    qwen_command = _command("JAPANMFA_REAL_QWEN_COMMAND", "JAPANMFA_REAL_QWEN_RUNTIME")
    mfa_command = _command("JAPANMFA_REAL_MFA_COMMAND", "JAPANMFA_REAL_MFA_RUNTIME")
    tdmelodic = os.environ.get("JAPANMFA_REAL_TDMELODIC_COMMAND")
    if not tdmelodic:
        pytest.skip("set JAPANMFA_REAL_TDMELODIC_COMMAND for the real pipeline")

    config = replace(
        config,
        asr=replace(config.asr, model=qwen_model),
        mfa=replace(
            config.mfa,
            acoustic_model=mfa_acoustic_model,
            g2p_model=mfa_g2p_model,
        ),
        commands=replace(config.commands, asr_worker=qwen_command, mfa=mfa_command),
        paths=replace(config.paths, cache_dir=tmp_path / "cache", output_dir=tmp_path / "output"),
    )
    mfa_root = os.environ.get("MFA_ROOT_DIR") or os.environ.get("JAPANMFA_REAL_MFA_ROOT")
    if mfa_root:
        monkeypatch.setenv("MFA_ROOT_DIR", mfa_root)
    result = JapanMFAPipeline(
        config,
        accent_client=TdmelodicClient(tuple(shlex.split(tdmelodic))),
    ).run(source, tmp_path / "output", None, limit=1)
    assert any(outcome.status == "aligned" for outcome in result.outcomes)
    _validate_real_artifact(tmp_path / "output", frozenset(config.validation.silence_labels))
