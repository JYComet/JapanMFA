"""Resumable Galgame OGG/WAV to edge-padded WAV and Japanese ASR text export.

Run one process per GPU with --shard INDEX --shards COUNT. Each shard owns
whole source categories, so output paths never overlap between workers.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from japanmfa.asr.timestamps import clean_asr_text
from japanmfa.postprocess import (
    _detect_silence_at_beginning_vec,
    _detect_silence_at_end_vec,
)


EXTENSIONS = {".ogg", ".wav"}


@dataclass(frozen=True)
class Item:
    source: Path
    relative: Path


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)


def record_error(log: Path, item: Item, exc: Exception) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    row = {"time": time.time(), "source": str(item.source), "error": repr(exc)}
    with log.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        stream.flush()


def output_paths(root: Path, relative: Path) -> tuple[Path, Path]:
    category, *rest = relative.parts
    inner = Path(*rest).with_suffix("")
    return root / category / "wav" / (str(inner) + ".wav"), root / category / "txt" / (str(inner) + ".txt")


def completed(wav: Path, txt: Path) -> bool:
    return wav.is_file() and txt.is_file() and wav.stat().st_size > 44 and txt.stat().st_size > 0


def prepare_audio(source: Path, destination: Path, edge_seconds: float) -> None:
    audio, rate = sf.read(source, dtype="float32", always_2d=True)
    if rate <= 0 or not len(audio):
        raise ValueError("empty audio or invalid sample rate")
    mono = audio[:, 0]
    leading = _detect_silence_at_beginning_vec(mono, rate, silence_threshold=0.001)
    trailing = _detect_silence_at_end_vec(mono, rate, silence_threshold=0.001)
    front = max(0, round((edge_seconds - leading) * rate))
    back = max(0, round((edge_seconds - trailing) * rate))
    if front or back:
        mono = np.pad(mono, (front, back))
    if rate != 16000:
        from scipy.signal import resample_poly

        factor = math.gcd(rate, 16000)
        mono = resample_poly(mono, 16000 // factor, rate // factor)
    sf.write(destination, mono, 16000, subtype="PCM_16")


def transcribe(model: object, paths: list[Path]) -> list[str]:
    try:
        results = model.transcribe(
            audio=[str(path) for path in paths],
            language=["Japanese"] * len(paths),
            return_time_stamps=False,
        )
    except Exception:
        if len(paths) == 1:
            raise
        middle = len(paths) // 2
        return transcribe(model, paths[:middle]) + transcribe(model, paths[middle:])
    if len(results) != len(paths):
        raise ValueError(f"ASR returned {len(results)} results for {len(paths)} inputs")
    texts = []
    for result in results:
        language = result.get("language") if isinstance(result, dict) else getattr(result, "language", None)
        raw = result.get("text") if isinstance(result, dict) else getattr(result, "text", None)
        if language != "Japanese" or not isinstance(raw, str):
            raise ValueError(f"ASR did not return Japanese text: {language!r}")
        value = clean_asr_text(raw).strip()
        if not value:
            raise ValueError("ASR returned empty Japanese text")
        texts.append(value)
    return texts


def iter_items(source: Path, categories: list[Path]):
    for category in categories:
        for current, dirs, files in os.walk(category):
            dirs.sort()
            for name in sorted(files):
                path = Path(current) / name
                if path.suffix.lower() in EXTENSIONS:
                    yield Item(path, path.relative_to(source))


def publish(local_wav: Path, text: str, wav: Path, txt: Path) -> None:
    wav.parent.mkdir(parents=True, exist_ok=True)
    txt.parent.mkdir(parents=True, exist_ok=True)
    token = f"{os.getpid()}.{time.time_ns()}"
    staged_wav = wav.with_name(f".{wav.stem}.{token}.partial.wav")
    staged_txt = txt.with_name(f".{txt.stem}.{token}.partial.txt")
    try:
        shutil.copyfile(local_wav, staged_wav)
        staged_txt.write_text(text + "\n", encoding="utf-8")
        os.replace(staged_wav, wav)
        os.replace(staged_txt, txt)
    finally:
        staged_wav.unlink(missing_ok=True)
        staged_txt.unlink(missing_ok=True)


def run(args: argparse.Namespace) -> None:
    source = args.input.resolve(strict=True)
    output = args.output.resolve(strict=True)
    if source == output or source in output.parents or output in source.parents:
        raise ValueError("input and output must be disjoint")
    if not (0 <= args.shard < args.shards):
        raise ValueError("shard must be in [0, shards)")
    categories = sorted((path for path in source.iterdir() if path.is_dir()), key=lambda p: p.name)
    categories = [category for index, category in enumerate(categories) if index % args.shards == args.shard]
    state_path = args.state / f"worker_{args.shard}.json"
    error_path = args.state / f"worker_{args.shard}_errors.jsonl"
    counts = {"done": 0, "skipped_existing": 0, "failed": 0, "categories": len(categories)}
    model = None
    last_item = ""

    def checkpoint(status: str) -> None:
        atomic_json(state_path, {**counts, "status": status, "last_item": last_item,
                                 "pid": os.getpid(), "updated_at": time.time()})

    def flush(items: list[Item]) -> None:
        nonlocal model, last_item
        if not items:
            return
        with tempfile.TemporaryDirectory(prefix=f"galgame-asr-{args.shard}-") as scratch:
            prepared = []
            for index, item in enumerate(items):
                last_item = str(item.relative)
                local_wav = Path(scratch) / f"{index}.wav"
                try:
                    prepare_audio(item.source, local_wav, args.edge_seconds)
                    prepared.append((item, local_wav))
                except Exception as exc:
                    counts["failed"] += 1
                    record_error(error_path, item, exc)
            if prepared:
                if model is None:
                    from japanmfa.asr.worker import _load_model
                    model = _load_model("Qwen/Qwen3-ASR-1.7B")
                try:
                    texts = transcribe(model, [path for _, path in prepared])
                    outcomes = list(zip(prepared, texts))
                except Exception:
                    outcomes = []
                    for item, local_wav in prepared:
                        try:
                            outcomes.append(((item, local_wav), transcribe(model, [local_wav])[0]))
                        except Exception as exc:
                            counts["failed"] += 1
                            record_error(error_path, item, exc)
                for (item, local_wav), text in outcomes:
                    try:
                        wav, txt = output_paths(output, item.relative)
                        publish(local_wav, text, wav, txt)
                        counts["done"] += 1
                    except Exception as exc:
                        counts["failed"] += 1
                        record_error(error_path, item, exc)
        checkpoint("running")

    checkpoint("starting")
    pending: list[Item] = []
    for item in iter_items(source, categories):
        last_item = str(item.relative)
        wav, txt = output_paths(output, item.relative)
        if completed(wav, txt):
            counts["skipped_existing"] += 1
            continue
        pending.append(item)
        if len(pending) >= args.batch_size:
            flush(pending)
            pending.clear()
    flush(pending)
    checkpoint("complete")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--shards", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--edge-seconds", type=float, default=0.5)
    args = parser.parse_args()
    if args.batch_size < 1 or not math.isfinite(args.edge_seconds) or args.edge_seconds < 0:
        parser.error("batch-size must be positive and edge-seconds finite and nonnegative")
    run(args)


if __name__ == "__main__":
    main()
