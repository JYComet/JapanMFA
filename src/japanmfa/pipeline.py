"""Japanese-only stage orchestration and per-utterance outcome isolation."""

from __future__ import annotations

import shutil
import stat
import json
import hashlib
import os
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .accent.parser import parse_accent
from .accent.tdmelodic import AccentRequest, TdmelodicClient
from .asr.qwen3 import ASRResult, Qwen3ASRClient
from .audio import AudioInfo, AudioNormalizer
from .cache import StageCache, stage_fingerprint
from .config import PipelineConfig
from .corpus import discover_utterances, load_source_text
from .domain import Mora, Pronunciation, SourceText, Token, Utterance, UtteranceOutcome
from .errors import SkipUtterance, StageFailure
from .frontend.japanese import JapaneseFrontend, render_locked_kana
from .frontend.mora import segment_morae
from .frontend.overrides import (
    ReadingOverrideSet,
    apply_reading_overrides,
    load_reading_overrides,
)
from .mfa.g2p import MfaG2pClient
from .mfa.lexicon import LockedLexicon
from .mfa.phone_map import PhoneMap
from .mfa.runner import MfaRunner
from .mfa.textgrid import MfaAlignment, parse_mfa_textgrid
from .output.reports import _redact_string, append_manifest, summarize, write_json
from .output.textgrid import validate_five_tier_textgrid, write_five_tier_textgrid
from .projection import project_annotations


@dataclass(frozen=True)
class BatchResult:
    outcomes: tuple[UtteranceOutcome, ...]
    manifest_path: Path
    summary_path: Path
    output_root: Path
    summary: Mapping[str, object]


def _source_from_asr(text: str) -> SourceText:
    processing = text.replace("\r\n", "").replace("\n", "").replace("\r", "").strip()
    return SourceText(original=text, processing=processing, source="asr")


def _duration(audio: AudioInfo, alignment: MfaAlignment) -> float:
    if audio.duration > 0:
        return audio.duration
    positive_ends = [phone.end for phone in alignment.phones]
    if positive_ends:
        return max(positive_ends)
    raise StageFailure("audio", "duration_unavailable", "audio duration is not positive")


def _valid_audio_artifact(path: Path) -> bool:
    try:
        metadata = path.stat()
    except OSError:
        return False
    return not path.is_symlink() and stat.S_ISREG(metadata.st_mode) and metadata.st_size > 0


def _token_payload(tokens: tuple[Token, ...]) -> list[dict[str, object]]:
    return [
        {
            "index": token.index,
            "start": token.start,
            "end": token.end,
            "surface": token.surface,
            "part_of_speech": list(token.part_of_speech),
            "reading": token.reading,
            "reading_source": token.reading_source,
        }
        for token in tokens
    ]


def _mora_payload(morae: Mapping[int, tuple[Mora, ...]]) -> list[dict[str, object]]:
    return [
        {
            "token_index": token_index,
            "morae": [
                {"index_in_token": mora.index_in_token, "kana": mora.kana, "tone": mora.tone}
                for mora in values
            ],
        }
        for token_index, values in sorted(morae.items())
    ]


def _adapter_id(adapter: object) -> str:
    def environment_identity(value: Mapping[object, object]) -> dict[str, object]:
        if any(not isinstance(key, str) for key in value):
            raise TypeError("string mapping keys are required for adapter identity")
        hashed: dict[str, object] = {}
        for key, raw in sorted(value.items()):
            rendered = str(raw)
            if os.environ.get(key) == rendered:
                continue
            digest = hashlib.sha256(f"{key}\0{rendered}".encode("utf-8")).hexdigest()
            hashed[key] = {"sha256": digest}
        return {"values": hashed}

    def stable(value: object) -> object:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, Mapping):
            if any(not isinstance(key, str) for key in value):
                raise TypeError("string mapping keys are required for adapter identity")
            return {str(key): stable(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
        if isinstance(value, (tuple, list)):
            return [stable(item) for item in value]
        if isinstance(value, (set, frozenset)):
            entries = [stable(item) for item in value]
            entries.sort(key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            return {"__type__": "set" if isinstance(value, set) else "frozenset", "items": entries}
        if hasattr(value, "__dict__"):
            return stable(vars(value))
        return f"{type(value).__module__}.{type(value).__qualname__}"

    state: dict[str, object] = {}
    for name, value in sorted(getattr(adapter, "__dict__", {}).items()):
        normalized = name.lstrip("_")
        if normalized in {"tokenizer", "runtime_object"} or callable(value):
            continue
        if normalized == "env" and isinstance(value, Mapping):
            state[normalized] = environment_identity(value)
            continue
        state[normalized] = stable(value)
    rendered = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{type(adapter).__module__}.{type(adapter).__qualname__}:{rendered}"


def _tokens_from_payload(payload: list[dict[str, object]]) -> tuple[Token, ...]:
    return tuple(
        Token(
            int(item["index"]),
            int(item["start"]),
            int(item["end"]),
            str(item["surface"]),
            tuple(str(value) for value in item.get("part_of_speech", [])),
            str(item["reading"]),
            str(item["reading_source"]),  # type: ignore[arg-type]
        )
        for item in payload
    )


def _morae_from_payload(payload: list[dict[str, object]]) -> dict[int, tuple[Mora, ...]]:
    result: dict[int, tuple[Mora, ...]] = {}
    for item in payload:
        token_index = int(item["token_index"])
        result[token_index] = tuple(
            Mora(token_index, int(value["index_in_token"]), str(value["kana"]), value.get("tone"))  # type: ignore[arg-type]
            for value in item["morae"]  # type: ignore[union-attr]
        )
    return result


class JapanMFAPipeline:
    """Run all Japanese alignment stages while isolating each utterance."""

    def __init__(
        self,
        config: PipelineConfig | None = None,
        *,
        audio_normalizer: Any | None = None,
        asr_client: Any | None = None,
        frontend: Any | None = None,
        accent_client: Any | None = None,
        g2p_client: Any | None = None,
        mfa_runner: Any | None = None,
        phone_map: PhoneMap | None = None,
        cache: Any | None = None,
    ) -> None:
        self.config = config or PipelineConfig()
        self.audio_normalizer = audio_normalizer
        self.asr_client = asr_client
        self.frontend = frontend
        self.accent_client = accent_client
        self.g2p_client = g2p_client
        self.mfa_runner = mfa_runner
        self.phone_map = phone_map
        self.cache = cache

    def _defaults(self, artifact_dir: Path) -> tuple[Any, ...]:
        audio = self.audio_normalizer or AudioNormalizer(self.config)
        asr = self.asr_client or Qwen3ASRClient(self.config.commands.asr_worker, self.config.asr.model)
        frontend = self.frontend or JapaneseFrontend()
        accent = self.accent_client or TdmelodicClient(("tdmelodic",))
        g2p = self.g2p_client or MfaG2pClient(self.config.commands.mfa, self.config.mfa.g2p_model)
        phone_map = self.phone_map or PhoneMap.load(
            Path(__file__).parent / "mfa" / "data" / "japanese_mfa_v3_phone_map.yaml"
        )
        mfa = self.mfa_runner
        if mfa is None:
            mfa = MfaRunner(
                self.config.commands.mfa,
                self.config.mfa.acoustic_model,
                owned_root=artifact_dir / "mfa",
            )
        return audio, asr, frontend, accent, g2p, mfa, phone_map

    def run(
        self,
        input_root: Path,
        output_root: Path,
        overrides: Path | None,
        *,
        limit: int | None = None,
    ) -> BatchResult:
        input_root = Path(input_root).resolve()
        output_root = Path(output_root).resolve()
        if input_root == output_root or input_root in output_root.parents:
            raise ValueError("output root must not be identical to or nested inside input root")
        if not input_root.is_dir():
            raise ValueError(f"input root is not a directory: {input_root}")
        utterances = discover_utterances(input_root)
        if limit is not None:
            if limit <= 0:
                raise ValueError("limit must be a positive integer")
            utterances = utterances[:limit]
        override_set = ReadingOverrideSet({}) if overrides is None else load_reading_overrides(Path(overrides).resolve())
        cache = self.cache or StageCache(Path(self.config.paths.cache_dir).resolve())
        output_root.mkdir(parents=True, exist_ok=True)
        manifest_path = output_root / "manifest.jsonl"
        if manifest_path.exists():
            manifest_path.unlink()
        outcomes: list[UtteranceOutcome] = []
        for utterance in utterances:
            outcome = self._run_utterance(utterance, output_root, override_set, cache)
            outcomes.append(outcome)
            append_manifest(manifest_path, outcome)
        summary = summarize(outcomes)
        summary_path = output_root / "summary.json"
        write_json(summary_path, summary)
        return BatchResult(tuple(outcomes), manifest_path, summary_path, output_root, summary)

    def _run_utterance(
        self,
        utterance: Utterance,
        output_root: Path,
        override_set: ReadingOverrideSet,
        cache: StageCache,
    ) -> UtteranceOutcome:
        started = time.monotonic()
        artifact_dir = output_root / utterance.utterance_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        durations: dict[str, float] = {}
        current_stage = "audio"
        try:
            audio, asr, frontend, accent, g2p, mfa, phone_map = self._defaults(artifact_dir)

            stage_started = time.monotonic()
            audio_fp = stage_fingerprint(
                "audio",
                {"audio": utterance.audio_path, "sample_rate": self.config.audio.sample_rate, "adapter": _adapter_id(audio)},
            )

            def produce_audio(path: Path) -> dict[str, object]:
                info = audio.prepare(utterance.audio_path, path / "audio.wav")
                return {
                    "duration": info.duration,
                    "source_sample_rate": info.source_sample_rate,
                    "source_channels": info.source_channels,
                    "working_sample_rate": info.working_sample_rate,
                }

            audio_meta = cache.load_or_run(
                "audio",
                audio_fp,
                produce_audio,
                validate=lambda directory: _valid_audio_artifact(directory / "audio.wav"),
            )
            cached_audio = cache.directory("audio", audio_fp) / "audio.wav"
            if not cached_audio.is_file():
                raise StageFailure("audio", "cache_artifact_missing", "cached working audio is missing")
            working_audio = artifact_dir / "work" / "audio.wav"
            working_audio.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cached_audio, working_audio)
            audio_info = AudioInfo(
                utterance.audio_path,
                working_audio,
                float(audio_meta["duration"]),
                int(audio_meta["source_sample_rate"]),
                int(audio_meta["source_channels"]),
                int(audio_meta["working_sample_rate"]),
            )
            durations["audio"] = time.monotonic() - stage_started

            current_stage = "source"
            stage_started = time.monotonic()
            source_fp = stage_fingerprint(
                "source",
                {
                    "audio": utterance.audio_path,
                    "text": utterance.text_path,
                    "model": self.config.asr.model,
                    "adapter": _adapter_id(asr),
                },
            )

            def produce_source(_path: Path) -> dict[str, object]:
                asr_result: ASRResult | None = None
                if utterance.text_path is not None:
                    source = load_source_text(utterance.text_path)
                    if asr is not None:
                        try:
                            asr_result = asr.transcribe([audio_info.working_path]).get(audio_info.working_path)
                        except StageFailure as exc:
                            if exc.stage == "asr" and exc.reason_code == "non_japanese_language":
                                raise SkipUtterance("non_japanese_language", exc.message, exc.details) from exc
                            raise
                else:
                    if asr is None:
                        raise StageFailure("asr", "unavailable", "ASR is required when .txt is missing")
                    try:
                        asr_result = asr.transcribe([audio_info.working_path]).get(audio_info.working_path)
                    except StageFailure as exc:
                        if exc.stage == "asr" and exc.reason_code == "non_japanese_language":
                            raise SkipUtterance("non_japanese_language", exc.message, exc.details) from exc
                        raise
                    if asr_result is None:
                        raise StageFailure("asr", "result_coverage_mismatch", "ASR returned no result")
                    source = _source_from_asr(asr_result.text)
                if asr_result is not None and asr_result.language != "Japanese":
                    raise SkipUtterance("unsupported_language", "ASR reported a non-Japanese language")
                return {
                    "original": source.original,
                    "processing": source.processing,
                    "source": source.source,
                    "asr": None if asr_result is None else {
                        "model": asr_result.model,
                        "language": asr_result.language,
                        "text": asr_result.text,
                    },
                }

            source_payload = cache.load_or_run("source", source_fp, produce_source)
            source = SourceText(str(source_payload["original"]), str(source_payload["processing"]), str(source_payload["source"]))  # type: ignore[arg-type]
            asr_payload = source_payload.get("asr")
            asr_result = None if asr_payload is None else ASRResult(audio_info.working_path, str(asr_payload["language"]), str(asr_payload["text"]), str(asr_payload["model"]))
            durations["source"] = time.monotonic() - stage_started
            write_json(
                artifact_dir / "asr.json",
                {
                    "model": None if asr_result is None else asr_result.model,
                    "language": None if asr_result is None else asr_result.language,
                    "text": None if asr_result is None else asr_result.text,
                    "source": source.source,
                    "authoritative_text": source.original,
                    "validation": "not_run" if asr_result is None else "language_checked",
                },
            )

            current_stage = "frontend"
            stage_started = time.monotonic()
            frontend_fp = stage_fingerprint(
                "frontend",
                {"source": source_payload, "overrides": _adapter_id(override_set), "adapter": _adapter_id(frontend)},
            )

            def produce_frontend(_path: Path) -> dict[str, object]:
                tokens = frontend.analyze(source)
                tokens = apply_reading_overrides(utterance.utterance_id, source.original, tokens, override_set)
                return {"tokens": _token_payload(tokens), "kana": render_locked_kana(source.original, tokens)}

            frontend_payload = cache.load_or_run("frontend", frontend_fp, produce_frontend)
            tokens = _tokens_from_payload(frontend_payload["tokens"])
            kana = str(frontend_payload["kana"])
            durations["frontend"] = time.monotonic() - stage_started
            write_json(artifact_dir / "frontend.json", {"tokens": _token_payload(tokens), "original": source.original, "kana": kana})

            current_stage = "accent"
            stage_started = time.monotonic()
            accent_fp = stage_fingerprint("accent", {"frontend": frontend_payload, "adapter": _adapter_id(accent)})

            def produce_accent(_path: Path) -> dict[str, object]:
                token_morae = {token.index: segment_morae(token) for token in tokens}
                requests = tuple(AccentRequest(token.index, token.surface, token.reading) for token in tokens)
                marked = accent.predict(requests)
                toned_morae: dict[int, tuple[Mora, ...]] = {}
                for token in tokens:
                    if token.index not in marked:
                        raise StageFailure("accent", "output_coverage_mismatch", "tdmelodic omitted a token", {"token_index": token.index})
                    toned_morae[token.index] = parse_accent(marked[token.index], token_morae[token.index])
                return {"morae": _mora_payload(toned_morae), "tdmelodic": marked}

            accent_payload = cache.load_or_run("accent", accent_fp, produce_accent)
            toned_morae = _morae_from_payload(accent_payload["morae"])
            marked = dict(accent_payload["tdmelodic"])
            durations["accent"] = time.monotonic() - stage_started
            write_json(artifact_dir / "mora.json", {"morae": _mora_payload(toned_morae), "tdmelodic": marked})

            current_stage = "g2p"
            stage_started = time.monotonic()
            g2p_fp = stage_fingerprint("g2p", {"tokens": _token_payload(tokens), "model": self.config.mfa.g2p_model, "adapter": _adapter_id(g2p)})

            def produce_g2p(path: Path) -> dict[str, object]:
                pronunciations = g2p.pronounce(tuple(token.reading for token in tokens), path)
                return {"pronunciations": [{"reading": item.reading, "phones": list(item.phones)} for item in pronunciations]}

            g2p_payload = cache.load_or_run("g2p", g2p_fp, produce_g2p)
            pronunciations = tuple(Pronunciation(str(item["reading"]), tuple(str(phone) for phone in item["phones"])) for item in g2p_payload["pronunciations"])
            lexicon = LockedLexicon.build(utterance.utterance_id, tokens, pronunciations)
            mfa_root = artifact_dir / "mfa"
            corpus_dir = mfa_root / "corpus"
            dictionary_path = mfa_root / "dictionary.dict"
            lexicon.write(corpus_dir, dictionary_path)
            corpus_audio = corpus_dir / f"{utterance.utterance_id}.wav"
            corpus_audio.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(audio_info.working_path, corpus_audio)
            durations["g2p"] = time.monotonic() - stage_started

            current_stage = "mfa"
            stage_started = time.monotonic()
            raw_grid = mfa.align(corpus_dir, dictionary_path, mfa_root / "aligned", mfa_root / "work")
            alignment = parse_mfa_textgrid(Path(raw_grid), frozenset(self.config.validation.silence_labels))
            durations["mfa"] = time.monotonic() - stage_started
            write_json(artifact_dir / "mfa.json", {"textgrid": str(raw_grid), "aliases": list(lexicon.aliases), "transcript": lexicon.transcript})

            current_stage = "projection"
            stage_started = time.monotonic()
            annotations = project_annotations(alignment, lexicon, toned_morae, phone_map)
            durations["projection"] = time.monotonic() - stage_started

            current_stage = "output"
            stage_started = time.monotonic()
            final_grid = artifact_dir / f"{Path(utterance.audio_path).stem}.TextGrid"
            duration = _duration(audio_info, alignment)
            write_five_tier_textgrid(final_grid, duration, source.original, kana, annotations)
            validate_five_tier_textgrid(final_grid, duration, frozenset(self.config.validation.silence_labels))
            write_json(
                artifact_dir / "alignment.json",
                {
                    "textgrid": str(final_grid),
                    "duration": duration,
                    "phones": [
                        {
                            "start": item.interval.start,
                            "end": item.interval.end,
                            "label": item.interval.label,
                            "kana": item.kana_label,
                            "tone": item.tone_label,
                            "token_index": item.token_index,
                            "silence": item.is_silence,
                        }
                        for item in annotations
                    ],
                },
            )
            durations["output"] = time.monotonic() - stage_started
            return UtteranceOutcome(utterance.utterance_id, "aligned", None, None, artifact_dir, durations)
        except SkipUtterance as exc:
            durations[current_stage] = durations.get(current_stage, time.monotonic() - started)
            return UtteranceOutcome(utterance.utterance_id, "skipped", exc.reason_code, exc.message, None, durations)
        except StageFailure as exc:
            durations[current_stage] = durations.get(current_stage, time.monotonic() - started)
            return UtteranceOutcome(utterance.utterance_id, "failed", exc.reason_code, exc.message, artifact_dir, durations)
        except Exception as exc:  # per-item isolation boundary
            durations[current_stage] = durations.get(current_stage, time.monotonic() - started)
            trace_path = artifact_dir / "traceback.txt"
            trace_path.write_text(_redact_string(traceback.format_exc()), encoding="utf-8")
            return UtteranceOutcome(
                utterance.utterance_id,
                "failed",
                "unexpected_exception",
                f"unexpected exception in {current_stage}: {exc}",
                artifact_dir,
                {**durations, "traceback": 0.0},
            )


__all__ = ["BatchResult", "JapanMFAPipeline"]
