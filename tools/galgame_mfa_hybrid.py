"""Whole-file MFA batch first; native CTC-anchor batch for failed candidates."""

from __future__ import annotations

import json
import os
import sys
import shutil
import time
from pathlib import Path
from dataclasses import replace
from typing import TYPE_CHECKING, Callable, Sequence
from concurrent.futures import ThreadPoolExecutor

if TYPE_CHECKING:
    from japanmfa.asr.precomputed_ctc import PrecomputedCTCClient
from japanmfa.accent.resident import ResidentAccentClient
from japanmfa.config import PipelineConfig
from japanmfa.domain import UtteranceOutcome
from japanmfa.mfa.g2p import MfaG2pClient, TerminalSokuonG2p
from japanmfa.mfa.hybrid_batch import BatchGridRunner, GroupedBatchRunner, build_dual_batch_corpus, build_batch_corpus
from japanmfa.mfa.runner import MfaRunner
from japanmfa.mfa.phone_map import PhoneMap
from japanmfa.mfa.failed_retry import failed_retry_command
from japanmfa.mfa.context_retry import prepare_context_retry, clipped_retry_inputs
from japanmfa.pipeline import JapanMFAPipeline
from tools.audit_textgrid_pauses import audit


_RETRY_REASONS = frozenset({
    "timestamp_mfa_disagreement", "alignment_acoustic_coverage",
    "phone_in_silence", "word_in_silence",
})


def needs_ctc_fallback(outcome: UtteranceOutcome) -> bool:
    """Retry only a checked alignment/energy rejection, never a model error."""
    if outcome.status != "failed" or outcome.reason_code not in _RETRY_REASONS or outcome.artifact_dir is None:
        return False
    report_path = outcome.artifact_dir / "postprocess.json"
    if not report_path.is_file():
        return False
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return report.get("passed") is False and report.get("reason_code") == outcome.reason_code


def choose_candidate(full: UtteranceOutcome, timed: UtteranceOutcome | None) -> str | None:
    if full.status == "aligned":
        return "whole"
    if timed is not None and timed.status == "aligned":
        return "anchored"
    return None


def existing_pair_verified(
    destination: Path, stem: str, source_sha256: str, sha: Callable[[Path], str],
) -> bool:
    grid = destination / f"{stem}.TextGrid"
    audio = destination / f"{stem}.wav"
    if not grid.is_file() or not audio.is_file() or sha(audio) != source_sha256:
        return False
    try:
        return bool(audit(grid)["passed"])
    except (OSError, ValueError, KeyError):
        return False


def _pipeline(config: PipelineConfig, adapter: PrecomputedCTCClient, *,
              runner: object | None = None, mode: str = "timed") -> JapanMFAPipeline:
    from japanmfa.asr.precomputed_ctc import OriginalAxisWav
    preparation_socket = os.environ.get("JAPANMFA_PREPARATION_SOCKET")
    command = config.commands.mfa
    accent = None
    if preparation_socket:
        command = (sys.executable, str(Path(__file__).parents[1] / "src/japanmfa/mfa/native_resident.py"), "call", preparation_socket)
        accent = ResidentAccentClient((*command, "accent"))
    elif os.environ.get("JAPANMFA_NATIVE_SOCKET"):
        accent = ResidentAccentClient((*command, "accent"))
    return JapanMFAPipeline(
        config, audio_normalizer=OriginalAxisWav(), asr_client=adapter,
        g2p_client=TerminalSokuonG2p(MfaG2pClient(command, config.mfa.g2p_model)),
        accent_client=accent,
        mfa_runner=runner, alignment_mode=mode, batch_preparation=True,
        preparation_workers=int(os.environ.get("JAPANMFA_PREPARATION_WORKERS", "1")),
        review_workers=int(os.environ.get("JAPANMFA_REVIEW_WORKERS", "1")),
        phone_map=PhoneMap.load(Path(__file__).parents[1] / "src/japanmfa/mfa/data/japanese_mfa_v3_phone_map.yaml"),
    )


def _batch_align(config: PipelineConfig, batch, *, socket: Path | None = None) -> tuple[dict[str, Path], float]:
    if socket is not None:
        command = (sys.executable, str(Path(__file__).parents[1] / "src/japanmfa/mfa/native_resident.py"),
                   "call", str(socket))
    elif os.environ.get("JAPANMFA_NATIVE_SOCKET"):
        command = config.commands.mfa
    else:
        command = failed_retry_command(config.commands.mfa)
    runner = MfaRunner(command, config.mfa.acoustic_model,
                       owned_root=batch.root.resolve(), dither=config.mfa.dither)
    started = time.monotonic()
    grids = runner.align_many(batch.corpus_dir, batch.dictionary,
                              batch.root / "aligned", batch.root / "work",
                              expected_stems=set(batch.entries),
                              external_validate=False, num_jobs=1, allow_partial=True)
    return grids, time.monotonic() - started


def _align_batches(config: PipelineConfig, batches: Sequence, sockets: Sequence[Path] | None
                   ) -> tuple[list[tuple[dict[str, Path], float]], float]:
    """Keep each one-job resident serial while independent residents run together."""
    started = time.monotonic()
    if sockets is None:
        outputs = [_batch_align(config, batch) for batch in batches]
    else:
        sockets = tuple(Path(value).resolve() for value in sockets)
        if len(sockets) != 2 or len(set(sockets)) != 2 or not all(path.is_socket() for path in sockets):
            raise ValueError("resident sockets must be two distinct live Unix sockets")
        with (ThreadPoolExecutor(max_workers=1) as first,
              ThreadPoolExecutor(max_workers=1) as second):
            executors = (first, second)
            futures = [executors[index % 2].submit(_batch_align, config, batch, socket=sockets[index % 2])
                       for index, batch in enumerate(batches)]
            outputs = [future.result() for future in futures]
    return outputs, time.monotonic() - started


def run_hybrid(
    stage: Path, rows: Sequence[dict[str, object]], run: Path, destination: Path,
    config: PipelineConfig, adapter: PrecomputedCTCClient,
    publish_pair: Callable[[dict[str, object], Path, Path, Path], dict[str, object]],
    sha: Callable[[Path], str],
) -> dict[str, object]:
    """Execute two possible MFA batches and preserve all per-item evidence."""
    started = time.monotonic()
    preparation = _pipeline(config, adapter).prepare_mfa_inputs(stage, run / "prepared", None)
    preparation_seconds = time.monotonic() - started
    prepared_by_id = {item.utterance_id: item for item in preparation.items}
    failures = {item.utterance_id: item for item in preparation.failures}
    if not preparation.items:
        raise ValueError("no utterance reached MFA input preparation")

    combined_batch, whole_batch, anchored_batch = build_dual_batch_corpus(
        preparation.items, run / "batch-dual",
    )
    batch_build_seconds = time.monotonic() - started - preparation_seconds
    all_grids, mfa_seconds = _batch_align(config, combined_batch)
    whole_provider = BatchGridRunner(
        whole_batch, {name: all_grids[name] for name in whole_batch.entries if name in all_grids},
        run / "hydrated-whole", allow_partial=True,
    )
    whole_stage = stage
    if failures:
        whole_stage = run / "whole-input"
        whole_stage.mkdir()
        for stem in sorted(prepared_by_id):
            for extension in (".wav", ".txt"):
                shutil.copy2(stage / f"{stem}{extension}", whole_stage / f"{stem}{extension}")
    full = _pipeline(config, adapter, runner=whole_provider, mode="whole").run(
        whole_stage, run / "pipeline-whole", None,
    )
    whole_review_seconds = time.monotonic() - started - preparation_seconds - batch_build_seconds - mfa_seconds
    full_outcomes = {item.utterance_id: item for item in full.outcomes}
    retry_ids = {stem for stem, outcome in full_outcomes.items()
                 if stem in prepared_by_id and needs_ctc_fallback(outcome)}

    anchored_outcomes: dict[str, UtteranceOutcome] = {}
    if retry_ids:
        anchored_provider = BatchGridRunner(
            anchored_batch, {name: all_grids[name] for name in anchored_batch.entries if name in all_grids},
            run / "hydrated-anchored", allow_partial=True,
        )
        retry_stage = run / "retry-input"
        retry_stage.mkdir()
        for stem in sorted(retry_ids):
            for extension in (".wav", ".txt"):
                shutil.copy2(stage / f"{stem}{extension}", retry_stage / f"{stem}{extension}")
        anchored = _pipeline(config, adapter, runner=anchored_provider, mode="whole").run(
            retry_stage, run / "pipeline-anchored", None,
        )
        anchored_outcomes = {item.utterance_id: item for item in anchored.outcomes}
    anchored_review_seconds = (time.monotonic() - started - preparation_seconds
                               - batch_build_seconds - mfa_seconds - whole_review_seconds)

    publication_started = time.monotonic()
    results: list[dict[str, object]] = []
    for row in rows:
        stem = str(row["stem"])
        full_outcome = full_outcomes.get(stem) or failures.get(stem)
        if full_outcome is None:
            raise ValueError(f"pipeline omitted {stem}")
        anchored_outcome = anchored_outcomes.get(stem)
        choice = choose_candidate(full_outcome, anchored_outcome)
        record: dict[str, object] = {
            "stem": stem, "whole_status": full_outcome.status,
            "whole_reason": full_outcome.reason_code,
            "anchored_attempted": stem in retry_ids,
            "anchored_status": None if anchored_outcome is None else anchored_outcome.status,
            "anchored_reason": None if anchored_outcome is None else anchored_outcome.reason_code,
            "chosen": choice, "published": False,
            "candidate_artifact": None if choice is None else str(run / f"pipeline-{choice}" / stem),
        }
        existing_grid = destination / f"{stem}.TextGrid"
        if existing_grid.exists():
            # A new alignment can fail without invalidating a previously accepted pair.
            if existing_pair_verified(destination, stem, str(row["wav_sha256"]), sha):
                record["retained_existing"] = True
                record["existing_textgrid_sha256"] = sha(existing_grid)
                record["published"] = True
            else:
                record["publication_error"] = "existing pair is incomplete or failed audit; preserved for review"
        if choice is not None:
            artifact = run / f"pipeline-{choice}" / stem
            candidate_grid = artifact / f"{stem}.TextGrid"
            candidate_audio = artifact / f"{stem}.wav"
            checked = audit(candidate_grid)
            if not checked["passed"] or sha(candidate_audio) != row["wav_sha256"]:
                record["publication_error"] = "candidate failed final audit or WAV hash check"
            elif existing_grid.exists():
                # Existing accepted artifacts are immutable during an experimental rerun.
                if record.get("retained_existing"):
                    record["candidate_textgrid_sha256"] = sha(candidate_grid)
            else:
                try:
                    record.update(publish_pair(row, artifact, destination, run / "before"))
                    record["published"] = True
                except (OSError, ValueError) as exc:
                    record["publication_error"] = str(exc)
        results.append(record)
    publication_seconds = time.monotonic() - publication_started

    report = {
        "strategy": "whole_first_ctc_fallback_single_load", "source_count": len(rows),
        "prepared_count": len(preparation.items), "preparation_failures": [
            {"stem": value.utterance_id, "reason": value.reason_code} for value in preparation.failures
        ],
        "mfa_batches": {
            "combined": {"files": len(combined_batch.entries), "seconds": mfa_seconds,
                         "jobs": 1, "external_validate": False},
            "whole": {"files": len(whole_batch.entries)},
            "anchored": {"files": len(anchored_batch.entries), "used": len(retry_ids)},
        },
        "fallback_stems": sorted(retry_ids),
        "phase_seconds": {
            "preparation": preparation_seconds,
            "batch_build": batch_build_seconds,
            "mfa_align": mfa_seconds,
            "whole_review": whole_review_seconds,
            "anchored_review": anchored_review_seconds,
            "publication": publication_seconds,
        },
        "results": results,
        "published_or_retained": sum(bool(value["published"]) for value in results),
        "newly_published": sum(bool(value["published"]) and not value.get("retained_existing") for value in results),
        "total_seconds": time.monotonic() - started,
        "destination": str(destination), "run_dir": str(run),
    }
    (run / "hybrid-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


__all__ = ["choose_candidate", "existing_pair_verified", "needs_ctc_fallback", "run_hybrid"]

def run_timed_batch(stage, rows, run, destination, config, adapter, publish_pair, sha, *, preparation=None,
                    acoustic_groups=None, resident_sockets=None):
    """Use the original CTC crop/restore path and preserve acoustic groups."""
    started = time.monotonic()
    if preparation is None:
        preparation = _pipeline(config, adapter, mode="timed").prepare_mfa_inputs(stage, run / "prepared", None)
    preparation_seconds = time.monotonic() - started
    if acoustic_groups is not None:
        listed = [stem for group in acoustic_groups for stem in group]
        if len(listed) != len(set(listed)) or set(listed) != {str(row["stem"]) for row in rows}:
            raise ValueError("acoustic groups must cover every source exactly once")
    outcomes = {x.utterance_id: x for x in preparation.failures}
    context_attempts = {}
    context_accepted = set()
    initial_grids = {}
    context_files = 0
    context_seconds = 0.0
    mfa_seconds = 0.0
    mfa_wall = 0.0
    initial_wall = 0.0
    context_wall = 0.0
    count = 0
    if preparation.items:
        groups = acoustic_groups or [[x.utterance_id for x in preparation.items]]
        if len({stem for group in groups for stem in group}) != sum(len(group) for group in groups):
            raise ValueError("duplicate acoustic group source")
        if set(x.utterance_id for x in preparation.items) - {stem for group in groups for stem in group}:
            raise ValueError("acoustic groups omitted prepared sources")
        providers = {}
        initial_batches = []
        initial_items = []
        for index, group in enumerate(groups):
            items = tuple(x for x in preparation.items if x.utterance_id in set(group))
            if not items:
                continue
            batch_root = run / "batch-timed" if len(groups) == 1 else run / "batch-timed" / str(index)
            batch = build_batch_corpus(items, batch_root, "timed")
            count += len(batch.entries)
            initial_batches.append(batch)
            initial_items.append((index, items))
        initial_outputs, initial_wall = _align_batches(config, initial_batches, resident_sockets)
        mfa_wall += initial_wall
        for (index, items), batch, (grids, seconds) in zip(initial_items, initial_batches, initial_outputs):
            mfa_seconds += seconds
            initial_grids.update({(entry.utterance_id, entry.segment_index): (entry, grids[name])
                                  for name, entry in batch.entries.items() if name in grids})
            native = BatchGridRunner(batch, grids, run / "hydrated-timed" / str(index), allow_partial=True)
            providers.update({x.utterance_id: native for x in items})
        provider = GroupedBatchRunner(providers)
        checked = _pipeline(config, adapter, runner=provider, mode="timed").review_mfa_inputs(
            preparation, run / "pipeline-timed")
        outcomes.update({x.utterance_id: x for x in checked.outcomes})
        retry_items = []
        for item in preparation.items:
            if needs_ctc_fallback(outcomes[item.utterance_id]):
                diagnostic = outcomes[item.utterance_id].artifact_dir / "postprocess.json"
                candidate = prepare_context_retry(item, failed_postprocess=(
                    json.loads(diagnostic.read_text()) if diagnostic.is_file() else None))
                if candidate is not None:
                    retry_items.append(candidate)
        retry_by_id = {item.utterance_id: item for item in retry_items}
        # Batch retries once; accepted original candidates never enter this path.
        providers = {}
        context_batches = []
        context_meta = []
        for index in range(0, len(retry_items), 500):
            items = tuple(retry_items[index:index + 500])
            batch = build_batch_corpus(items, run / "batch-context" / str(index // 500), "timed")
            changed = {item.utterance_id: set(item.state.values["native_retry_segments"])
                       for item in items if item.state.values.get("clipped_tail_context")}
            native_batch, reused = clipped_retry_inputs(batch, initial_grids, changed)
            context_files += len(native_batch.entries)
            context_batches.append(native_batch)
            context_meta.append((index, items, batch, reused))
        context_outputs, context_wall = _align_batches(config, context_batches, resident_sockets)
        mfa_wall += context_wall
        for (index, items, batch, reused), (grids, seconds) in zip(context_meta, context_outputs):
            grids.update(reused)
            mfa_seconds += seconds
            context_seconds += seconds
            native = BatchGridRunner(batch, grids, run / "hydrated-context" / str(index // 500), allow_partial=True)
            providers.update({x.utterance_id: native for x in items})
        if retry_items:
            retry_preparation = replace(preparation, items=tuple(retry_items), failures=())
            retried = _pipeline(config, adapter, runner=GroupedBatchRunner(providers), mode="timed").review_mfa_inputs(
                retry_preparation, run / "pipeline-context")
            for outcome in retried.outcomes:
                context_attempts[outcome.utterance_id] = {
                    "status": outcome.status, "reason": outcome.reason_code,
                    "artifact": str(outcome.artifact_dir),
                    "original_reason": outcomes[outcome.utterance_id].reason_code,
                }
                context = retry_by_id[outcome.utterance_id].state.values.get("clipped_tail_context")
                if context:
                    context_attempts[outcome.utterance_id]["clipped_tail_context"] = context
                    original_report = outcomes[outcome.utterance_id].artifact_dir / "postprocess.json"
                    context_attempts[outcome.utterance_id]["original_postprocess"] = str(original_report)
                    context_attempts[outcome.utterance_id]["original_postprocess_sha256"] = sha(original_report)
                # The already-running outer scanner always archives this full report.
                # Keep diagnostics here as well as the separate postprocess file.
                diagnostic = outcome.artifact_dir / "postprocess.json"
                if diagnostic.is_file():
                    context_attempts[outcome.utterance_id]["postprocess"] = json.loads(diagnostic.read_text())
                    context_attempts[outcome.utterance_id]["postprocess_sha256"] = sha(diagnostic)
                if outcome.status == "aligned":
                    outcomes[outcome.utterance_id] = outcome
                    context_accepted.add(outcome.utterance_id)
    review_seconds = time.monotonic() - started - preparation_seconds - mfa_wall
    publication_started = time.monotonic()
    results = []
    for row in rows:
        stem = str(row["stem"])
        outcome = outcomes[stem]
        record = {"stem": stem, "whole_status": outcome.status,
                  "whole_reason": outcome.reason_code, "timed_status": outcome.status,
                  "timed_reason": outcome.reason_code, "anchored_attempted": False,
                  "anchored_status": None, "anchored_reason": None, "chosen": None,
                  "published": False, "candidate_artifact": None}
        if stem in context_attempts:
            record["context_retry"] = context_attempts[stem]
        if outcome.status == "aligned":
            artifact = run / ("pipeline-context" if stem in context_accepted else "pipeline-timed") / stem
            grid, audio = artifact / (stem + ".TextGrid"), artifact / (stem + ".wav")
            if not audit(grid)["passed"] or sha(audio) != row["wav_sha256"]:
                record["publication_error"] = "candidate failed final audit or WAV hash check"
            else:
                try:
                    record.update(publish_pair(row, artifact, destination, run / "before"))
                    record.update(published=True, chosen="timed_context" if stem in context_accepted else "timed", candidate_artifact=str(artifact))
                except (OSError, ValueError) as exc:
                    record["publication_error"] = str(exc)
        results.append(record)
    report = {"strategy": "ctc_timed_batch_resident", "source_count": len(rows),
              "prepared_count": len(preparation.items),
              "preparation_failures": [{"stem": x.utterance_id, "reason": x.reason_code}
                                       for x in preparation.failures],
              "mfa_batches": {"timed": {"files": count, "seconds": initial_wall,
                                        "service_seconds": mfa_seconds - context_seconds,
                                        "jobs": 1, "batches": len(acoustic_groups or [1])},
                              "context_retry": {"files": context_files, "seconds": context_wall,
                                                "service_seconds": context_seconds,
                                                "sources": len(context_attempts), "accepted": len(context_accepted), "jobs": 1}},
              "resident_count": 2 if resident_sockets is not None else 1,
              "results": results, "published_or_retained": sum(x["published"] for x in results),
              "newly_published": sum(x["published"] for x in results),
              "phase_seconds": {"preparation": preparation_seconds, "mfa_align": mfa_wall,
                                "mfa_align_service_sum": mfa_seconds,
                                "timed_review": review_seconds,
                                "publication": time.monotonic() - publication_started},
              "total_seconds": time.monotonic() - started,
              "run_dir": str(run), "destination": str(destination)}
    (run / "hybrid-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report
