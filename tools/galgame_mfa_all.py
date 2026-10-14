"""Resume MFA over complete JapGalgame WAV/TXT/CTC triples.

Only audited final TextGrids are published under GalgameMFA/<game>/.
All reports, rejected-item evidence and temporary WAVs stay in local --state.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import uuid
import wave
from contextlib import ExitStack
from tools.preparation_windows import PreparationWindows
from dataclasses import dataclass
from itertools import zip_longest
from pathlib import Path
from typing import Callable, Iterator, Sequence

from japanmfa.asr.precomputed_ctc import read_ctc_words
from tools.audit_textgrid_pauses import audit


REPO = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Triple:
    game: str
    relative_stem: Path
    wav: Path
    txt: Path
    ctc: Path

    @property
    def key(self) -> str:
        return f"{self.game}/{self.relative_stem.as_posix()}"


def discover_triples(source: Path, *, stats: dict[str, int] | None = None) -> Iterator[Triple]:
    """Stream completed triples in game/path order without a 6M-item manifest."""
    stats = {} if stats is None else stats
    for game in sorted(source.iterdir(), key=lambda path: path.name):
        wav_root = game / "wav"
        if not game.is_dir() or not wav_root.is_dir() or game.is_symlink():
            continue
        for current, dirs, files in os.walk(wav_root, followlinks=False):
            dirs[:] = sorted(name for name in dirs if not (Path(current) / name).is_symlink())
            for name in sorted(files):
                if not name.lower().endswith(".wav"):
                    continue
                wav = Path(current) / name
                if wav.is_symlink():
                    continue
                relative = wav.relative_to(wav_root).with_suffix("")
                txt = game / "txt" / relative.parent / f"{relative.name}.txt"
                ctc = game / "ctc" / relative.parent / f"{relative.name}.TextGrid"
                if not txt.is_file() or not ctc.is_file():
                    stats["incomplete"] = stats.get("incomplete", 0) + 1
                    continue
                stats["complete"] = stats.get("complete", 0) + 1
                yield Triple(game.name, relative, wav, txt, ctc)


def discover_manifest_triples(manifests: Sequence[Path], source: Path, *,
                              stats: dict[str, int] | None = None) -> Iterator[Triple]:
    """Read the existing local CTC catalogs; interleave shards fairly."""
    if not manifests:
        raise ValueError("at least one manifest is required")
    stats = {} if stats is None else stats
    with ExitStack() as stack:
        streams = [stack.enter_context(path.open("r", encoding="utf-8")) for path in manifests]
        for group in zip_longest(*streams):
            for line in group:
                if line is None:
                    continue
                row = json.loads(line)
                game = str(row["category"])
                relative = Path(str(row["stem"]))
                if (not game or Path(game).name != game or relative.is_absolute()
                        or not relative.parts or ".." in relative.parts):
                    raise ValueError(f"unsafe game/stem in manifest: {game}/{relative}")
                base = source / game
                expected = (base / "wav" / relative.parent / f"{relative.name}.wav",
                            base / "txt" / relative.parent / f"{relative.name}.txt",
                            base / "ctc" / relative.parent / f"{relative.name}.TextGrid")
                actual = (Path(row["wav"]), Path(row["txt"]), Path(row["ctc"]))
                if actual != expected:
                    raise ValueError(f"manifest input paths differ from source tree: {game}/{relative}")
                if not all(path.is_file() for path in actual):
                    stats["incomplete"] = stats.get("incomplete", 0) + 1
                    continue
                stats["complete"] = stats.get("complete", 0) + 1
                yield Triple(game, relative, *actual)


def source_signature(item: Triple) -> str:
    return json.dumps([(path.stat().st_size, path.stat().st_mtime_ns)
                       for path in (item.wav, item.txt, item.ctc)], separators=(",", ":"))


def preflight_source(item: Triple) -> None:
    """Reject a bad member before it can abort an entire MFA batch."""
    with wave.open(str(item.wav), "rb") as audio:
        if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate(),
                audio.getcomptype()) != (1, 2, 16000, "NONE") or audio.getnframes() < 1:
            raise ValueError("WAV must be nonempty mono PCM16 16 kHz")
        duration = audio.getnframes() / audio.getframerate()
    reference = item.txt.read_text(encoding="utf-8-sig")
    if not reference.strip():
        raise ValueError("TXT is empty")
    read_ctc_words(item.ctc, reference, duration)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _alias(item: Triple) -> str:
    return "u" + hashlib.sha256(item.key.encode("utf-8")).hexdigest()[:24]


def _init_db(connection: sqlite3.Connection) -> None:
    connection.execute("""CREATE TABLE IF NOT EXISTS items (
        key TEXT PRIMARY KEY, signature TEXT NOT NULL, status TEXT NOT NULL,
        output_sha256 TEXT, reason TEXT, batch_id TEXT NOT NULL
    )""")
    connection.commit()


def _record(connection: sqlite3.Connection, item: Triple, signature: str, status: str,
            batch_id: str, *, output_sha256: str | None = None, reason: str | None = None) -> None:
    connection.execute("""INSERT INTO items VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET signature=excluded.signature, status=excluded.status,
        output_sha256=excluded.output_sha256, reason=excluded.reason, batch_id=excluded.batch_id""",
        (item.key, signature, status, output_sha256, reason, batch_id))
    connection.commit()


def _atomic_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink() or target.parent.is_symlink():
        raise ValueError(f"refusing symlink output: {target}")
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.partial")
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _output_path(output: Path, item: Triple) -> Path:
    return output / item.game / item.relative_stem.parent / f"{item.relative_stem.name}.TextGrid"


def _archive_old(output: Path, item: Triple, state: Path, batch_id: str,
                 *, remove: bool = True) -> None:
    old = _output_path(output, item)
    if old.exists():
        archived = state / "obsolete" / batch_id / item.game / item.relative_stem.parent / old.name
        _atomic_copy(old, archived)
        if remove:
            old.unlink()


def _subprocess_phase(stage: Path, aliases: list[str], run: Path,
                      destination: Path, config: Path, *, prepare=False, use_prepared=False) -> int:
    cache_dir = stage.parent / "cache" if prepare or use_prepared else stage.parents[2] / "cache"
    command = [sys.executable, "-u", str(REPO / "tools/galgame_mfa_from_ctc.py"),
               str(stage), "--stems", *aliases, "--alignment-strategy", os.environ.get("JAPANMFA_ALIGNMENT_STRATEGY", "hybrid"),
               "--config", str(config), "--run-dir", str(run), "--output", str(destination),
               "--cache-dir", str(cache_dir)]
    if prepare:
        command.append("--prepare-only")
    if use_prepared:
        command.extend(("--use-prepared", "--acoustic-groups", str(stage.parent / "acoustic-groups.json")))
    environment = os.environ.copy()
    if prepare:
        environment["MFA_ROOT_DIR"] = environment["JAPANMFA_PREPARATION_ROOT"]
        environment["JAPANMFA_NATIVE_SOCKET"] = environment["JAPANMFA_PREPARATION_SOCKET"]
    environment["PYTHONPATH"] = os.pathsep.join((str(REPO / "src"), str(REPO),
                                                 environment.get("PYTHONPATH", "")))
    with (stage.parent / ("prepare.log" if prepare else "align.log")).open("w", encoding="utf-8") as log:
        return subprocess.run(command, cwd=REPO, env=environment, stdout=log,
                              stderr=subprocess.STDOUT, check=False).returncode


def _subprocess_align(stage, aliases, run, destination, config):
    return _subprocess_phase(stage, aliases, run, destination, config)


def _stage_batch(items, state, acoustic_size=500):
    batch_id = uuid.uuid4().hex
    work = state / "work" / batch_id
    stage, run, candidate = work / "source", work / "run", work / "candidate"
    aliases: dict[str, tuple[Triple, str]] = {}
    for folder in ("wav", "txt", "ctc"):
        (stage / folder).mkdir(parents=True, exist_ok=True)
    for item, signature in items:
        alias = _alias(item)
        if alias in aliases:
            raise ValueError(f"batch alias collision: {item.key}")
        aliases[alias] = (item, signature)
        for folder, extension, source in (("wav", ".wav", item.wav),
                                          ("txt", ".txt", item.txt),
                                          ("ctc", ".TextGrid", item.ctc)):
            (stage / folder / f"{alias}{extension}").symlink_to(source)
    groups = [sorted(_alias(item) for item, _ in items[index:index+acoustic_size])
              for index in range(0, len(items), acoustic_size)]
    (work / "acoustic-groups.json").write_text(json.dumps(groups))
    return {"items": items, "batch_id": batch_id, "work": work, "stage": stage,
            "run": run, "candidate": candidate, "aliases": aliases}


def _run_batch(items: list[tuple[Triple, str]], output: Path, state: Path,
               config: Path, connection: sqlite3.Connection,
               align: Callable[[Path, list[str], Path, Path, Path], int],
               counts: dict[str, int]) -> None:
    batch = _stage_batch(items, state)
    code = align(batch["stage"], sorted(batch["aliases"]), batch["run"], batch["candidate"], config)
    _commit_batch(batch, code, output, state, config, connection, counts)


def _commit_batch(batch, code, output, state, config, connection, counts, *, private_cache=False):
    items, batch_id, work, stage, run, candidate, aliases = (
        batch[name] for name in ("items", "batch_id", "work", "stage", "run", "candidate", "aliases"))
    snapshot_to_remove = None
    snapshot_root = os.environ.get("JAPANMFA_NVME_SNAPSHOT_ROOT")
    input_stage = run / "input"
    if snapshot_root and input_stage.is_symlink():
        expected = Path(snapshot_root).resolve() / batch_id / "input"
        if input_stage.resolve() != expected:
            raise RuntimeError(f"unexpected snapshot target: {input_stage}")
        snapshot_to_remove = expected.parent
    report_path = run / "hybrid-report.json"
    if code not in (0, 1) or not report_path.is_file():
        raise RuntimeError(f"MFA batch {batch_id} failed before a complete report; see {work / 'align.log'}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    rows = {row["stem"]: row for row in report["results"]}
    if set(rows) != set(aliases) or len(report["results"]) != len(aliases):
        raise RuntimeError(f"MFA batch {batch_id} report omitted or duplicated items")
    config_signature = _sha(config) if config.is_file() else str(config)
    for item, signature in items:
        if source_signature(item) + ":" + config_signature != signature:
            raise RuntimeError(f"source changed during MFA batch {batch_id}: {item.key}")
    archive = state / "reports" / f"{batch_id}.json"
    archive.parent.mkdir(parents=True, exist_ok=True)
    input_timing_path = run / "input-timings.json"
    input_timing = json.loads(input_timing_path.read_text()) if input_timing_path.is_file() else None
    archive.write_text(json.dumps({"items": {alias: item.key for alias, (item, _) in aliases.items()},
                                   "report": report, "input_timing": input_timing},
                                  ensure_ascii=False) + "\n", encoding="utf-8")
    for alias, (item, signature) in aliases.items():
        row = rows[alias]
        reason = row.get("whole_reason") or row.get("anchored_reason") or row.get("publication_error")
        grid = candidate / f"{alias}.TextGrid"
        rejection = None
        if not row.get("published") or not grid.is_file():
            rejection = str(reason or "no accepted candidate")
        else:
            try:
                if not audit(grid)["passed"]:
                    rejection = "final acoustic/structural audit failed"
            except (OSError, ValueError, RuntimeError) as exc:
                rejection = f"final audit error: {exc}"
        if rejection is not None:
            _archive_old(output, item, state, batch_id)
            diagnostic = state / "filtered" / item.game / item.relative_stem.parent / f"{item.relative_stem.name}.json"
            diagnostic.parent.mkdir(parents=True, exist_ok=True)
            for mode in ("whole", "anchored", "timed", "context"):
                source_report = run / f"pipeline-{mode}" / alias / "postprocess.json"
                if source_report.is_file():
                    shutil.copy2(source_report, diagnostic.with_name(
                        f"{item.relative_stem.name}.{mode}-postprocess.json"))
            diagnostic.write_text(json.dumps({"source": item.key, "wav": str(item.wav),
                                              "txt": str(item.txt), "ctc": str(item.ctc),
                                              "reason": rejection, "pipeline": row,
                                              "batch_report": str(archive)}, ensure_ascii=False) + "\n",
                                  encoding="utf-8")
            _record(connection, item, signature, "filtered", batch_id, reason=rejection)
            counts["filtered"] += 1
            continue
        target = _output_path(output, item)
        _archive_old(output, item, state, batch_id, remove=False)
        _atomic_copy(grid, target)
        old_diagnostic = state / "filtered" / item.game / item.relative_stem.parent / f"{item.relative_stem.name}.json"
        if old_diagnostic.is_file():
            resolved = state / "resolved" / batch_id / item.game / item.relative_stem.parent / old_diagnostic.name
            resolved.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(old_diagnostic, resolved)
        _record(connection, item, signature, "passed", batch_id,
                output_sha256=_sha(target))
        counts["published"] += 1
    print(json.dumps({"batch": batch_id, "items": len(items), "published_total": counts["published"],
                      "filtered_total": counts["filtered"]}, ensure_ascii=False), flush=True)
    shutil.rmtree(work)
    if snapshot_to_remove is not None:
        shutil.rmtree(snapshot_to_remove)
    audio_cache = state / "cache" / "audio"
    if not private_cache and audio_cache.is_dir():
        shutil.rmtree(audio_cache)


def run_all(source: Path, output: Path, state: Path, config: Path, *, batch_size: int = 500,
            max_items: int | None = None, retry_filtered: bool = False,
            reprocess_all: bool = False,
            manifests: Sequence[Path] | None = None,
            align: Callable[[Path, list[str], Path, Path, Path], int] = _subprocess_align) -> dict[str, int]:
    if batch_size < 1 or (max_items is not None and max_items < 1):
        raise ValueError("batch-size and max-items must be positive")
    state.mkdir(parents=True, exist_ok=True)
    config_signature = _sha(config) if config.is_file() else str(config)
    counts = {"complete": 0, "incomplete": 0, "published": 0, "filtered": 0,
              "skipped_existing": 0, "skipped_filtered": 0, "preflight_failed": 0}
    with (state / "job.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("another full-corpus MFA process is using this state directory") from exc
        connection = sqlite3.connect(state / "progress.sqlite3")
        try:
            _init_db(connection)
            optimized = bool(os.environ.get("JAPANMFA_PREPARATION_SOCKET")) and align is _subprocess_align
            window_size = int(os.environ.get("JAPANMFA_PREPARATION_WINDOW", str(batch_size))) if optimized else batch_size
            if window_size < batch_size or window_size % batch_size:
                raise ValueError("preparation window must contain whole acoustic batches")
            with ExitStack() as stack:
                if optimized:
                    def prepare(batch):
                        return _subprocess_phase(batch["stage"], sorted(batch["aliases"]), batch["run"],
                                                 batch["candidate"], config, prepare=True)
                    def align_prepared(batch):
                        return _subprocess_phase(batch["stage"], sorted(batch["aliases"]), batch["run"],
                                                 batch["candidate"], config, use_prepared=True)
                    def commit(batch, code):
                        _commit_batch(batch, code, output, state, config, connection, counts, private_cache=True)
                    windows = stack.enter_context(PreparationWindows(prepare, align_prepared, commit))
                    def submit(items):
                        windows.submit(_stage_batch(items, state, batch_size))
                else:
                    def submit(items):
                        _run_batch(items, output, state, config, connection, align, counts)
                pending: list[tuple[Triple, str]] = []
                selected = 0
                catalog = (discover_manifest_triples(manifests, source, stats=counts)
                           if manifests else discover_triples(source, stats=counts))
                for item in catalog:
                    signature = source_signature(item) + ":" + config_signature
                    previous = connection.execute("SELECT signature, status, output_sha256 FROM items WHERE key=?",
                                                  (item.key,)).fetchone()
                    target = _output_path(output, item)
                    if previous and previous[0] == signature and not reprocess_all:
                        if previous[1] == "passed" and target.is_file() and _sha(target) == previous[2]:
                            counts["skipped_existing"] += 1
                            continue
                        if previous[1] == "filtered" and not retry_filtered and not target.exists():
                            counts["skipped_filtered"] += 1
                            continue
                    try:
                        preflight_source(item)
                    except (OSError, EOFError, UnicodeError, ValueError, wave.Error) as exc:
                        batch_id = "preflight-" + uuid.uuid4().hex
                        _archive_old(output, item, state, batch_id)
                        diagnostic = state / "filtered" / item.game / item.relative_stem.parent / f"{item.relative_stem.name}.json"
                        diagnostic.parent.mkdir(parents=True, exist_ok=True)
                        diagnostic.write_text(json.dumps({"source": item.key, "wav": str(item.wav),
                                                          "txt": str(item.txt), "ctc": str(item.ctc),
                                                          "reason": f"preflight: {exc}"}, ensure_ascii=False) + "\n",
                                              encoding="utf-8")
                        _record(connection, item, signature, "filtered", batch_id, reason=f"preflight: {exc}")
                        counts["preflight_failed"] += 1
                        selected += 1
                    else:
                        pending.append((item, signature))
                        selected += 1
                        if len(pending) >= window_size:
                            submit(list(pending))
                            pending.clear()
                    if max_items is not None and selected >= max_items:
                        break
                if pending:
                    submit(list(pending))
        finally:
            connection.close()
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("/mnt/Raw/JapGalgame"))
    parser.add_argument("--output", type=Path, default=Path("/mnt/Raw/GalgameMFA"))
    parser.add_argument("--state", type=Path, default=REPO / ".runtime/jobs/galgame-mfa-all")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--max-items", type=int, help="process at most this many new/changed triples")
    parser.add_argument("--retry-filtered", action="store_true")
    parser.add_argument("--reprocess-all", action="store_true",
                        help="recheck every complete triple after a pipeline code change")
    parser.add_argument("--manifest", type=Path, action="append",
                        help="use one or more local CTC catalog shard files instead of scanning SMB directories")
    parser.add_argument("--dry-run", action="store_true", help="count complete triples only; never start MFA")
    args = parser.parse_args()
    source, output, state, config = (path.resolve() for path in
                                     (args.source, args.output, args.state, args.config))
    if not source.is_dir() or not config.is_file():
        parser.error("source directory and config file must exist")
    if source == output or source in output.parents or output in source.parents:
        parser.error("output must be outside the source tree")
    if source == state or source in state.parents or output == state or output in state.parents:
        parser.error("state must be outside source and output trees")
    if args.dry_run:
        counts: dict[str, int] = {}
        catalog = (discover_manifest_triples(args.manifest, source, stats=counts)
                   if args.manifest else discover_triples(source, stats=counts))
        for index, _item in enumerate(catalog, 1):
            if args.max_items is not None and index >= args.max_items:
                break
        print(json.dumps(counts, ensure_ascii=False), flush=True)
        return 0
    counts = run_all(source, output, state, config, batch_size=args.batch_size,
                     max_items=args.max_items, retry_filtered=args.retry_filtered,
                     reprocess_all=args.reprocess_all, manifests=args.manifest)
    print(json.dumps(counts, ensure_ascii=False), flush=True)
    return 0 if not (counts["filtered"] or counts["preflight_failed"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
