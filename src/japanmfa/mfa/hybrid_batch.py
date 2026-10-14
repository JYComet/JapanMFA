"""Build isolated multi-file MFA corpora and restore per-utterance aliases."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import wave
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, Sequence

from japanmfa.errors import StageFailure
from japanmfa.mfa.textgrid import parse_mfa_textgrid
from japanmfa.pipeline import MfaPrepared


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class BatchEntry:
    name: str
    utterance_id: str
    segment_index: int | None
    local_aliases: tuple[str, ...]
    global_aliases: tuple[str, ...]
    wav_sha256: str


@dataclass(frozen=True)
class BatchCorpus:
    kind: Literal["whole", "timed", "anchored", "dual"]
    root: Path
    corpus_dir: Path
    dictionary: Path
    entries: dict[str, BatchEntry]


def _write_crop(source: Path, destination: Path, start: float, end: float) -> None:
    with wave.open(str(source), "rb") as audio:
        rate = audio.getframerate()
        if audio.getnchannels() != 1 or audio.getsampwidth() != 2 or rate <= 0:
            raise StageFailure("mfa", "invalid_working_audio", "batch crop requires mono PCM16 audio")
        first = max(0, min(audio.getnframes(), round(start * rate)))
        last = max(0, min(audio.getnframes(), round(end * rate)))
        if last <= first:
            raise StageFailure("mfa", "invalid_timed_segment", "batch crop has no samples")
        audio.setpos(first)
        frames = audio.readframes(last - first)
    with wave.open(str(destination), "wb") as output:
        output.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        output.writeframes(frames)


def _write_anchor_grid(item: MfaPrepared, destination: Path, remap: dict[str, str]) -> None:
    """Expose CTC windows as stock MFA speaker-tier utterances on full audio."""
    with wave.open(str(item.corpus_audio), "rb") as audio:
        duration = audio.getnframes() / audio.getframerate()
    rows = [
        'File type = "ooTextFile"', 'Object class = "TextGrid"', '',
        'xmin = 0', f'xmax = {duration}', 'tiers? <exists>', 'size = 1',
        'item []:', '    item [1]:', '        class = "IntervalTier"',
        '        name = "speaker"', '        xmin = 0', f'        xmax = {duration}',
        f'        intervals: size = {len(item.segments)}',
    ]
    cursor = 0.0
    for index, segment in enumerate(item.segments, 1):
        if not (cursor <= segment.start < segment.end <= duration + 1e-6):
            raise StageFailure("mfa", "invalid_timed_segment", "anchor windows overlap or exceed full WAV")
        aliases = item.aliases[segment.first_token:segment.last_token]
        if not aliases:
            raise StageFailure("mfa", "batch_alias_mismatch", "anchor window has no words")
        rows.extend([
            f'        intervals [{index}]:',
            f'            xmin = {segment.start}',
            f'            xmax = {min(duration, segment.end)}',
            f'            text = "{" ".join(remap[alias] for alias in aliases)}"',
        ])
        cursor = segment.end
    destination.write_text("\n".join(rows) + "\n", encoding="utf-8")


def build_batch_corpus(
    items: Sequence[MfaPrepared], root: Path, kind: Literal["whole", "timed", "anchored"],
) -> BatchCorpus:
    """Write one MFA corpus with occurrence-unique aliases across all WAVs."""
    if kind not in {"whole", "timed", "anchored"} or not items:
        raise ValueError("batch requires items and a whole, timed, or anchored kind")
    root = Path(root)
    corpus = root / "corpus"
    corpus.mkdir(parents=True, exist_ok=False)
    dictionary = root / "dictionary.dict"
    dictionary_rows: list[str] = []
    entries: dict[str, BatchEntry] = {}
    seen_ids: set[str] = set()
    next_alias = 0
    for file_index, item in enumerate(sorted(items, key=lambda value: value.utterance_id)):
        if item.utterance_id in seen_ids:
            raise ValueError("duplicate utterance in MFA batch")
        seen_ids.add(item.utterance_id)
        local = tuple(item.aliases)
        lab = item.corpus_audio.with_suffix(".lab")
        if tuple(lab.read_text().split()) != local:
            raise StageFailure("mfa", "batch_alias_mismatch", "locked lab differs from preparation")
        remap = {alias: f"jmfa_{next_alias + index:06d}" for index, alias in enumerate(local)}
        next_alias += len(local)
        if len(remap) != len(local):
            raise StageFailure("mfa", "batch_alias_mismatch", "duplicate local alias")
        for row in item.dictionary.read_text().splitlines():
            alias, separator, phones = row.partition(" ")
            if not separator or alias not in remap:
                raise StageFailure("mfa", "batch_dictionary_mismatch", "dictionary contains an unknown alias")
            dictionary_rows.append(f"{remap[alias]} {phones}")
        chunks = [(None, local, None)] if kind in {"whole", "anchored"} else [
            (index, local[segment.first_token:segment.last_token], segment)
            for index, segment in enumerate(item.segments)
        ]
        for segment_index, aliases, segment in chunks:
            name = f"b{file_index:04d}" + ("" if segment_index is None else f"_{segment_index:03d}")
            wav = corpus / f"{name}.wav"
            if segment is None:
                shutil.copy2(item.corpus_audio, wav)
            else:
                _write_crop(item.working_audio, wav, segment.start, segment.end)
            if kind == "anchored":
                _write_anchor_grid(item, corpus / f"{name}.TextGrid", remap)
            else:
                (corpus / f"{name}.lab").write_text(" ".join(remap[a] for a in aliases) + "\n")
            entries[name] = BatchEntry(name, item.utterance_id, segment_index,
                                       tuple(aliases), tuple(remap[a] for a in aliases), _sha(wav))
    dictionary.write_text("\n".join(dictionary_rows) + "\n")
    (root / "manifest.json").write_text(json.dumps({
        "kind": kind, "dictionary_sha256": _sha(dictionary),
        "entries": [{**vars(entry), "local_aliases": list(entry.local_aliases),
                     "global_aliases": list(entry.global_aliases)} for entry in entries.values()],
    }, ensure_ascii=False, indent=2) + "\n")
    return BatchCorpus(kind, root, corpus, dictionary, entries)


def build_dual_batch_corpus(
    items: Sequence[MfaPrepared], root: Path,
) -> tuple[BatchCorpus, BatchCorpus, BatchCorpus]:
    """Place whole and anchored views in one MFA corpus and model load."""
    root = Path(root)
    whole_source = build_batch_corpus(items, root / "whole", "whole")
    anchored_source = build_batch_corpus(items, root / "anchored", "anchored")
    if _sha(whole_source.dictionary) != _sha(anchored_source.dictionary):
        raise StageFailure("mfa", "batch_dictionary_mismatch", "whole and anchored dictionaries differ")
    combined_root = root / "combined"
    corpus = combined_root / "corpus"
    corpus.mkdir(parents=True, exist_ok=False)
    dictionary = combined_root / "dictionary.dict"
    shutil.copy2(whole_source.dictionary, dictionary)
    views: list[BatchCorpus] = []
    all_entries: dict[str, BatchEntry] = {}
    for source, prefix in ((whole_source, "w"), (anchored_source, "a")):
        entries: dict[str, BatchEntry] = {}
        for entry in source.entries.values():
            name = prefix + entry.name
            for extension in (".wav", ".lab", ".TextGrid"):
                old = source.corpus_dir / f"{entry.name}{extension}"
                if old.is_file():
                    shutil.copy2(old, corpus / f"{name}{extension}")
            if _sha(corpus / f"{name}.wav") != entry.wav_sha256:
                raise StageFailure("mfa", "batch_audio_mismatch", "combined corpus changed the complete WAV")
            entries[name] = replace(entry, name=name)
            all_entries[name] = entries[name]
        views.append(BatchCorpus(source.kind, combined_root, corpus, dictionary, entries))
    combined = BatchCorpus("dual", combined_root, corpus, dictionary, all_entries)
    (combined_root / "manifest.json").write_text(json.dumps({
        "kind": "dual", "dictionary_sha256": _sha(dictionary),
        "entries": [{**vars(entry), "local_aliases": list(entry.local_aliases),
                     "global_aliases": list(entry.global_aliases)} for entry in all_entries.values()],
    }, ensure_ascii=False, indent=2) + "\n")
    return combined, views[0], views[1]


class BatchGridRunner:
    """Serve already-batched MFA grids through the pipeline's runner API."""

    def __init__(self, batch: BatchCorpus, grids: dict[str, Path], hydrated_root: Path,
                 *, allow_partial: bool = False) -> None:
        if set(grids) - set(batch.entries) or (not allow_partial and set(grids) != set(batch.entries)):
            raise StageFailure("mfa", "output_coverage_mismatch", "batch grids do not cover every input")
        self.batch = batch
        self.grids = dict(grids)
        self.hydrated_root = Path(hydrated_root)

    def align(self, corpus_dir: Path, _dictionary: Path, _output_dir: Path, _work_dir: Path) -> Path:
        labs = list(Path(corpus_dir).glob("*.lab"))
        if len(labs) != 1:
            raise StageFailure("mfa", "batch_input_mismatch", "expected one locked lab in pipeline corpus")
        utterance_id = labs[0].stem
        segment_index = None if self.batch.kind != "timed" else int(Path(corpus_dir).parent.name)
        matches = [entry for entry in self.batch.entries.values()
                   if entry.utterance_id == utterance_id and entry.segment_index == segment_index]
        if len(matches) != 1:
            raise StageFailure("mfa", "batch_input_mismatch", "no matching batch TextGrid")
        entry = matches[0]
        if tuple(labs[0].read_text().split()) != entry.local_aliases:
            raise StageFailure("mfa", "batch_alias_mismatch", "pipeline lab differs from batch input")
        wav = Path(corpus_dir) / f"{utterance_id}.wav"
        if _sha(wav) != entry.wav_sha256:
            raise StageFailure("mfa", "batch_audio_mismatch", "pipeline WAV differs from batch input")
        if entry.name not in self.grids:
            raise StageFailure("mfa", "missing_output", "MFA produced no TextGrid for this input",
                               {"batch_entry": entry.name, "utterance_id": utterance_id})
        raw = self.grids[entry.name].read_text(encoding="utf-8")
        remap = dict(zip(entry.global_aliases, entry.local_aliases))
        pattern = re.compile(r'(?m)^(\s*text\s*=\s*)"([^"]+)"(\s*)$')
        hydrated = pattern.sub(lambda match: match.group(1) + json.dumps(remap.get(match.group(2), match.group(2)))
                               + match.group(3), raw)
        self.hydrated_root.mkdir(parents=True, exist_ok=True)
        path = self.hydrated_root / f"{entry.name}.TextGrid"
        path.write_text(hydrated, encoding="utf-8")
        parsed = parse_mfa_textgrid(path, frozenset({""}))
        if tuple(word.alias for word in parsed.words) != entry.local_aliases:
            raise StageFailure("mfa", "batch_alias_mismatch", "MFA words differ from locked batch aliases")
        return path


class GroupedBatchRunner:
    """Route one locked utterance to its immutable precomputed-grid provider."""

    def __init__(self, providers: dict[str, BatchGridRunner]) -> None:
        self.providers = dict(providers)

    def align(self, corpus: Path, dictionary: Path, output: Path, work: Path) -> Path:
        labs = list(Path(corpus).glob("*.lab"))
        if len(labs) != 1 or labs[0].stem not in self.providers:
            raise ValueError("prepared acoustic provider mismatch")
        return self.providers[labs[0].stem].align(corpus, dictionary, output, work)


__all__ = ["BatchCorpus", "BatchEntry", "BatchGridRunner", "GroupedBatchRunner", "build_batch_corpus", "build_dual_batch_corpus"]
