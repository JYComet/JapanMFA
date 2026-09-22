# JapanMFA Japanese Five-Track Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an independent Japanese-only pipeline that locks kana readings, predicts mora H/L with tdmelodic, aligns phones with Japanese MFA v3, and exports validated five-tier TextGrids plus audit reports.

**Architecture:** A small Python orchestrator owns corpus discovery, immutable domain records, validation, caching, projection, and output. Qwen3-ASR, tdmelodic, and MFA run behind subprocess adapters in isolated runtimes; data crosses those boundaries as JSON, line-oriented text, dictionary files, and TextGrid files. Every successful utterance has one traceable path from source text through locked morae to the final MFA phone intervals.

**Tech Stack:** Python 3.11, hatchling, Typer, PyYAML, SudachiPy + sudachidict-core, praatio, pytest, Qwen3-ASR 1.7B/0.6B, Montreal Forced Aligner 3.x with Japanese MFA v3 models, tdmelodic, FFmpeg.

**Spec:** `docs/superpowers/specs/2026-09-22-japanmfa-japanese-five-track-design.md`

## Global Constraints

- Work only in the new `JapanMFA` repository; do not modify or import source from `/home/user/JapMFA`.
- Keep `main` based on the clean root commit `7a4f7ca`; execute feature work in an isolated `codex/` branch/worktree.
- The first release supports Japanese only. Any unsupported non-Japanese utterance is `skipped`, never partially aligned.
- `.txt` is authoritative when present. Qwen3-ASR validates it; ASR supplies candidate text only when `.txt` is absent.
- Qwen3-ASR is locked to `Japanese`; default model is `Qwen/Qwen3-ASR-1.7B`, with `Qwen/Qwen3-ASR-0.6B` configurable.
- SudachiPy `SplitMode.B` supplies default readings; per-occurrence YAML overrides lock corrections.
- tdmelodic is called only through `sy2a(surface, yomi)` per token and must not replace the locked reading.
- Japanese MFA v3 is the only final time-boundary authority; Qwen Forced Aligner is not used.
- Final TextGrids contain exactly `original`, `kana`, `phones`, `phone_kana`, and `phone_tone` in that order.
- `original` and `kana` each contain one full-duration interval. The last three tiers have identical interval counts and boundaries.
- Every non-silence phone has non-empty kana and tone. Multi-mora phones use ordered labels such as `オ|ー` and `H|L`.
- Input corpora remain read-only. Temporary and final artifacts live under JapanMFA-owned output/cache directories.
- All implementation work follows TDD and ends each task with focused tests plus a logical commit.

## Review Focus

- UTF-8 BOM, trailing newlines, and multi-line `.txt` files must normalize deterministically without changing the saved original text; Task 2 pins this behavior.
- A forced-Japanese ASR result that still contains Latin text or an unpronounceable token must be `skipped`, not passed to MFA; Tasks 3 and 4 pin this behavior.
- Duplicate basenames in different speaker directories and case-fold collisions must retain distinct stable utterance IDs or fail discovery clearly; Task 2 pins this behavior.
- MFA TextGrids containing `sil`, `sp`, `spn`, empty intervals, or zero-duration intervals must be classified and validated without shifting neighboring boundaries; Task 7 pins this behavior.
- Malformed tdmelodic brackets and a single MFA long phone spanning differently toned morae must fail or produce an ordered composite without inventing a boundary; Tasks 5 and 8 pin this behavior.

---

## Planned File Structure

```text
pyproject.toml                         Package metadata, dependencies, CLI entry point
.gitignore                             Generated artifacts, models, caches, environments
environment.yml                        Orchestrator environment
environments/mfa.yml                   Isolated MFA environment
environments/asr.yml                   Isolated Qwen3-ASR environment
configs/default.yaml                   Default models, commands, paths, validation settings
src/japanmfa/domain.py                 Immutable cross-stage domain records and enums
src/japanmfa/errors.py                 Typed expected pipeline errors
src/japanmfa/config.py                 YAML configuration loading and validation
src/japanmfa/corpus.py                 Corpus discovery and source-text loading
src/japanmfa/audio.py                  Read-only audio inspection and FFmpeg working copies
src/japanmfa/asr/qwen3.py              Qwen subprocess client and response validation
src/japanmfa/asr/worker.py             Qwen runtime JSONL worker
src/japanmfa/frontend/japanese.py       Sudachi tokenization and support decisions
src/japanmfa/frontend/overrides.py      Span-addressed reading overrides
src/japanmfa/frontend/mora.py           Kana normalization and mora segmentation
src/japanmfa/accent/tdmelodic.py        Batched sy2a command adapter
src/japanmfa/accent/parser.py           Bracketed accent to mora H/L parser
src/japanmfa/mfa/g2p.py                 Japanese MFA G2P command adapter
src/japanmfa/mfa/lexicon.py             Occurrence aliases, transcript, locked dictionary
src/japanmfa/mfa/runner.py              MFA validate/align invocation
src/japanmfa/mfa/textgrid.py            Raw MFA word/phone tier parser
src/japanmfa/projection.py              Word/mora/phone reconciliation and H/L projection
src/japanmfa/output/textgrid.py          Final five-tier writer and validator
src/japanmfa/output/reports.py           Per-utterance and batch JSON/JSONL reports
src/japanmfa/cache.py                   Content fingerprints and atomic stage publication
src/japanmfa/pipeline.py                Stage orchestration and outcome isolation
src/japanmfa/checks.py                  Runtime/model/preflight checks
src/japanmfa/cli.py                     Typer commands
tools/build_tdmelodic_image.sh           Reproducible isolated tdmelodic build wrapper
tests/unit/...                           Pure unit tests
tests/contract/...                       External command contract tests with fake executables
tests/integration/...                    Opt-in model/audio integration tests
tests/fixtures/...                       Tiny text, JSON, dictionary, and TextGrid fixtures
docs/architecture.md                     Runtime and data-flow documentation
docs/input-output.md                     Corpus, five-tier, and report contracts
docs/reading-overrides.md                Override authoring and validation
docs/accent-mapping.md                   tdmelodic/mora/phone mapping rules
docs/limitations.md                      Explicit unsupported and uncovered behavior
docs/test-report-0922jap.md              Real-corpus evidence and findings
```

### Task 1: Package Skeleton, Domain Records, and Configuration

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/japanmfa/__init__.py`
- Create: `src/japanmfa/domain.py`
- Create: `src/japanmfa/errors.py`
- Create: `src/japanmfa/config.py`
- Create: `configs/default.yaml`
- Test: `tests/unit/test_config.py`
- Test: `tests/unit/test_domain.py`

**Interfaces:**
- Produces: `PipelineConfig.load(path: Path) -> PipelineConfig`
- Produces: `Utterance`, `SourceText`, `Token`, `Mora`, `Pronunciation`, `PhoneInterval`, `PhoneAnnotation`, `UtteranceOutcome`
- Produces: `OutcomeStatus = aligned | skipped | failed` and typed `SkipUtterance`/`StageFailure`

- [ ] **Step 1: Write failing configuration and domain tests**

```python
def test_default_config_locks_required_models(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "asr:\n  model: Qwen/Qwen3-ASR-1.7B\n  language: Japanese\n"
        "mfa:\n  acoustic_model: japanese_mfa\n  g2p_model: japanese_mfa\n"
        "audio:\n  sample_rate: 16000\n",
        encoding="utf-8",
    )
    config = PipelineConfig.load(path)
    assert config.asr.language == "Japanese"
    assert config.mfa.acoustic_model == "japanese_mfa"


def test_phone_interval_rejects_negative_duration() -> None:
    with pytest.raises(ValueError, match="end must be greater"):
        PhoneInterval(start=1.0, end=1.0, label="a")
```

- [ ] **Step 2: Run the focused tests and verify collection/import failure**

Run: `pytest tests/unit/test_config.py tests/unit/test_domain.py -q`  
Expected: FAIL because `japanmfa.config` and `japanmfa.domain` do not exist.

- [ ] **Step 3: Add package metadata and immutable domain records**

Use Python 3.11, hatchling, a `src/` layout, and the CLI entry point `japanmfa = "japanmfa.cli:app"`. Define frozen dataclasses with these stable fields:

```python
@dataclass(frozen=True)
class Utterance:
    utterance_id: str
    audio_path: Path
    text_path: Path | None

@dataclass(frozen=True)
class SourceText:
    original: str
    processing: str
    source: Literal["txt", "asr"]

@dataclass(frozen=True)
class Token:
    index: int
    start: int
    end: int
    surface: str
    part_of_speech: tuple[str, ...]
    reading: str
    reading_source: Literal["sudachi", "override"]

@dataclass(frozen=True)
class Mora:
    token_index: int
    index_in_token: int
    kana: str
    tone: Literal["H", "L"] | None = None

@dataclass(frozen=True)
class Pronunciation:
    reading: str
    phones: tuple[str, ...]

@dataclass(frozen=True)
class PhoneInterval:
    start: float
    end: float
    label: str

@dataclass(frozen=True)
class PhoneAnnotation:
    interval: PhoneInterval
    token_index: int | None
    morae: tuple[Mora, ...]
    kana_label: str
    tone_label: str
    is_silence: bool

@dataclass(frozen=True)
class UtteranceOutcome:
    utterance_id: str
    status: OutcomeStatus
    reason_code: str | None
    message: str | None
    artifact_dir: Path | None
    stage_durations: Mapping[str, float]
```

Define `SkipUtterance(reason_code, message, details)` for unsupported inputs and `StageFailure(stage, reason_code, message, details)` for supported inputs that fail.

- [ ] **Step 4: Implement typed YAML configuration loading**

Reject unknown top-level keys and any language other than `Japanese`. Store external commands as argument arrays, never shell strings. `configs/default.yaml` must name the 1.7B ASR model, 0.6B fallback, Japanese MFA models, 16 kHz working audio, silence labels `["", "sil", "sp", "spn"]`, and project-owned cache/output defaults.

- [ ] **Step 5: Run tests and static package checks**

Run: `pytest tests/unit/test_config.py tests/unit/test_domain.py -q`  
Expected: PASS.  
Run: `python -m compileall -q src`  
Expected: exit 0.

- [ ] **Step 6: Commit the package foundation**

```bash
git add pyproject.toml .gitignore configs src/japanmfa tests/unit/test_config.py tests/unit/test_domain.py
git commit -m "feat: establish JapanMFA domain and configuration"
```

### Task 2: Corpus Discovery, Text Semantics, and Working Audio

**Files:**
- Create: `src/japanmfa/corpus.py`
- Create: `src/japanmfa/audio.py`
- Test: `tests/unit/test_corpus.py`
- Test: `tests/contract/test_audio.py`
- Create: `tests/fixtures/bin/fake_ffmpeg.py`

**Interfaces:**
- Consumes: `Utterance`, `SourceText`, `PipelineConfig`
- Produces: `discover_utterances(root: Path) -> list[Utterance]`
- Produces: `load_source_text(path: Path) -> SourceText`
- Produces: `AudioNormalizer.prepare(source: Path, destination: Path) -> AudioInfo`

`AudioInfo` is a frozen record with `source_path`, `working_path`, `duration`, `source_sample_rate`, `source_channels`, and `working_sample_rate`.

- [ ] **Step 1: Write discovery and text-normalization tests**

```python
def test_duplicate_basenames_get_relative_ids(corpus: Path) -> None:
    touch_wav(corpus / "a" / "001.wav")
    touch_wav(corpus / "b" / "001.wav")
    assert [u.utterance_id for u in discover_utterances(corpus)] == ["a/001", "b/001"]


def test_source_text_preserves_original_and_normalizes_processing_copy(tmp_path: Path) -> None:
    path = tmp_path / "x.txt"
    path.write_bytes(b"\xef\xbb\xbf\xe4\xbb\x8a\xe6\x97\xa5\r\n\xe3\x81\xaf\xe6\x99\xb4\xe3\x82\x8c\r\n")
    text = load_source_text(path)
    assert text.original == "今日\r\nは晴れ\r\n"
    assert text.processing == "今日は晴れ"
```

Also test deterministic lexical ordering, unsupported extensions ignored, symlinked audio rejected by default, and case-fold ID collision raising `StageFailure("discovery", "duplicate_utterance_id", ...)`.

- [ ] **Step 2: Run tests to verify the missing-module failure**

Run: `pytest tests/unit/test_corpus.py -q`  
Expected: FAIL because `japanmfa.corpus` does not exist.

- [ ] **Step 3: Implement read-only corpus discovery and source loading**

Use `Path.rglob("*.wav")`, resolve paths only for comparison, and never write beneath `root`. Strip exactly one UTF-8 BOM from the processing copy, normalize CRLF/newlines to no separator for one-utterance processing, trim surrounding whitespace from the processing copy, and retain decoded source content excluding the BOM as `original`.

- [ ] **Step 4: Write the failing FFmpeg command contract test**

The fake executable must record argv and create the requested destination. Assert `-nostdin`, `-ac 1`, `-ar 16000`, `-c:a pcm_s16le`, an explicit source path, and an explicit destination path are passed without `shell=True`.

- [ ] **Step 5: Implement `AudioNormalizer` with atomic destination publication**

Write to `destination.with_suffix(".partial.wav")`, verify it exists and is non-empty, then `os.replace` it. Use `subprocess.run(argv, check=True, capture_output=True, text=True)` and convert nonzero exits into `StageFailure("audio", "ffmpeg_failed", ...)`.

- [ ] **Step 6: Run focused tests and commit**

Run: `pytest tests/unit/test_corpus.py tests/contract/test_audio.py -q`  
Expected: PASS.

```bash
git add src/japanmfa/corpus.py src/japanmfa/audio.py tests/unit/test_corpus.py tests/contract/test_audio.py tests/fixtures/bin/fake_ffmpeg.py
git commit -m "feat: discover Japanese corpus inputs safely"
```

### Task 3: Qwen3-ASR Adapter and Japanese-Locked Worker

**Files:**
- Create: `src/japanmfa/asr/__init__.py`
- Create: `src/japanmfa/asr/qwen3.py`
- Create: `src/japanmfa/asr/worker.py`
- Test: `tests/contract/test_qwen3_client.py`
- Test: `tests/unit/test_qwen3_worker.py`
- Create: `tests/fixtures/bin/fake_qwen_worker.py`

**Interfaces:**
- Produces: `ASRResult(audio_path: Path, language: str, text: str, model: str)`
- Produces: `Qwen3ASRClient.transcribe(audio_paths: Sequence[Path]) -> dict[Path, ASRResult]`
- Worker protocol: one JSON request on stdin, one JSON response on stdout; stderr is diagnostic only.

- [ ] **Step 1: Write a failing client protocol test**

```python
def test_client_forces_japanese_and_preserves_order(fake_worker: Path, tmp_path: Path) -> None:
    client = Qwen3ASRClient(command=[sys.executable, str(fake_worker)], model="Qwen/Qwen3-ASR-1.7B")
    paths = [tmp_path / "a.wav", tmp_path / "b.wav"]
    results = client.transcribe(paths)
    assert results[paths[0]].language == "Japanese"
    assert results[paths[0]].text == "今日は晴れ"
```

Test malformed JSON, duplicate/missing result paths, a reported non-Japanese language, and nonzero worker exit. Each must become `StageFailure("asr", ...)`.

- [ ] **Step 2: Run the contract test and observe import failure**

Run: `pytest tests/contract/test_qwen3_client.py -q`  
Expected: FAIL because the adapter is absent.

- [ ] **Step 3: Implement the subprocess client**

The request schema is:

```json
{"model":"Qwen/Qwen3-ASR-1.7B","language":"Japanese","audio_paths":["/abs/a.wav"]}
```

The response schema is:

```json
{"results":[{"audio_path":"/abs/a.wav","language":"Japanese","text":"今日は晴れ"}]}
```

Require absolute paths, exact one-to-one result coverage, and `language == "Japanese"`. Do not accept a free-form mixed stdout stream.

- [ ] **Step 4: Write worker unit tests around an injected fake model**

Define `transcribe_request(request: dict, model_factory: Callable) -> dict`. Assert `model.transcribe(audio=[...], language=["Japanese", ...], return_time_stamps=False)` is called and results are converted to the protocol above.

- [ ] **Step 5: Implement the real worker entry point**

Import `torch` and `Qwen3ASRModel` only inside the worker. Initialize `Qwen3ASRModel.from_pretrained(model, dtype=torch.bfloat16, device_map="cuda:0", max_inference_batch_size=32, max_new_tokens=256)`, then call `model.transcribe(audio=[...], language=["Japanese", ...])`. Keep model loading isolated in `_load_model` so unit tests inject a fake. Do not configure a forced aligner or request timestamps because MFA owns final boundaries.

- [ ] **Step 6: Run tests and commit**

Run: `pytest tests/contract/test_qwen3_client.py tests/unit/test_qwen3_worker.py -q`  
Expected: PASS without Qwen weights installed.

```bash
git add src/japanmfa/asr tests/contract/test_qwen3_client.py tests/unit/test_qwen3_worker.py tests/fixtures/bin/fake_qwen_worker.py
git commit -m "feat: add Japanese-locked Qwen3 ASR adapter"
```

### Task 4: Sudachi Frontend and Per-Occurrence Reading Overrides

**Files:**
- Create: `src/japanmfa/frontend/__init__.py`
- Create: `src/japanmfa/frontend/japanese.py`
- Create: `src/japanmfa/frontend/overrides.py`
- Test: `tests/unit/test_japanese_frontend.py`
- Test: `tests/unit/test_overrides.py`

**Interfaces:**
- Consumes: `SourceText`
- Produces: `JapaneseFrontend.analyze(text: SourceText) -> tuple[Token, ...]`
- Produces: `load_reading_overrides(path: Path) -> ReadingOverrideSet`
- Produces: `apply_reading_overrides(utterance_id: str, original: str, tokens: tuple[Token, ...], overrides: ReadingOverrideSet) -> tuple[Token, ...]`

- [ ] **Step 1: Write failing Japanese support tests**

```python
def test_sudachi_mode_b_returns_locked_katakana(frontend: JapaneseFrontend) -> None:
    tokens = frontend.analyze(SourceText(original="今日は晴れ", processing="今日は晴れ", source="txt"))
    assert "".join(t.surface for t in tokens) == "今日は晴れ"
    assert all(re.fullmatch(r"[ァ-ヿー]+", t.reading) for t in tokens)


@pytest.mark.parametrize("text", ["Tokyoへ行く", "hello", "日本語🙂"])
def test_non_japanese_or_unknown_input_is_skipped(frontend: JapaneseFrontend, text: str) -> None:
    with pytest.raises(SkipUtterance, match="unsupported_japanese_text"):
        frontend.analyze(SourceText(original=text, processing=text, source="txt"))
```

Include a numeric token that Sudachi converts to valid katakana and must pass. Punctuation must remain represented in metadata but not become a pronounced token.

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest tests/unit/test_japanese_frontend.py -q`  
Expected: FAIL due to missing frontend.

- [ ] **Step 3: Implement the Sudachi frontend**

Construct `Dictionary(dict="core").create(mode=SplitMode.B)`. Reject ASCII Latin letters before tokenization. For each non-symbol morpheme require a non-empty `reading_form()` matching normalized katakana. Preserve exact spans against `SourceText.processing`; if the tokenizer cannot be reconciled to source positions, raise `StageFailure("frontend", "token_span_mismatch", ...)`.

- [ ] **Step 4: Write failing override tests**

Test a valid `今日` override, span out of range, mismatched surface, overlapping overrides, duplicate entries, invalid kana, and two occurrences where only the selected character span changes.

- [ ] **Step 5: Implement strict YAML override application**

Parse `span` as a half-open `[start, end]` pair. Validate all overrides before applying any. Replace only the target token's reading; require override boundaries to match one complete pronounced token in v1. Set `reading_source="override"`.

- [ ] **Step 6: Run frontend tests and commit**

Run: `pytest tests/unit/test_japanese_frontend.py tests/unit/test_overrides.py -q`  
Expected: PASS.

```bash
git add src/japanmfa/frontend tests/unit/test_japanese_frontend.py tests/unit/test_overrides.py
git commit -m "feat: lock Japanese token readings"
```

### Task 5: Mora Segmentation and tdmelodic Accent Parsing

**Files:**
- Create: `src/japanmfa/frontend/mora.py`
- Create: `src/japanmfa/accent/__init__.py`
- Create: `src/japanmfa/accent/tdmelodic.py`
- Create: `src/japanmfa/accent/parser.py`
- Test: `tests/unit/test_mora.py`
- Test: `tests/unit/test_accent_parser.py`
- Test: `tests/contract/test_tdmelodic.py`
- Create: `tests/fixtures/bin/fake_tdmelodic.py`

**Interfaces:**
- Produces: `segment_morae(token: Token) -> tuple[Mora, ...]`
- Produces: `AccentRequest(token_index: int, surface: str, yomi: str)`
- Produces: `TdmelodicClient.predict(requests: Sequence[AccentRequest]) -> dict[int, str]`
- Produces: `parse_accent(marked_yomi: str, locked_morae: tuple[Mora, ...]) -> tuple[Mora, ...]`

- [ ] **Step 1: Write exhaustive mora tests**

```python
@pytest.mark.parametrize(
    ("kana", "expected"),
    [
        ("キョウ", ["キョ", "ウ"]),
        ("ガッコウ", ["ガ", "ッ", "コ", "ウ"]),
        ("コンピューター", ["コ", "ン", "ピュ", "ー", "タ", "ー"]),
        ("ファイル", ["ファ", "イ", "ル"]),
    ],
)
def test_segment_morae(kana: str, expected: list[str]) -> None:
    assert [m.kana for m in segment_morae(token(kana))] == expected
```

Reject a leading combining small kana and unsupported code points.

- [ ] **Step 2: Implement mora segmentation and pass its tests**

Run before implementation: `pytest tests/unit/test_mora.py -q` (FAIL). Implement an explicit small-kana set and special standalone set `{ッ, ン, ー}`. Run again and expect PASS.

- [ ] **Step 3: Write failing accent parser tests**

Cover `キ[カイガ]クシュー`, an initial-high form with an early `]`, a heiban-like final high run, unmatched/nested brackets, two rises without a fall, a marker inside a mora digraph, and marked reading unequal to locked reading. Assert the result contains exactly one `H`/`L` per locked mora.

- [ ] **Step 4: Implement boundary-event parsing**

Convert hiragana/katakana to one canonical katakana form before equality checking. Parse markers only between complete morae. If the first event is a fall, initialize pitch at H; otherwise initialize at L. `[` sets subsequent pitch H and `]` sets subsequent pitch L. Reject structurally impossible event sequences instead of repairing them.

- [ ] **Step 5: Write and implement the batched tdmelodic command contract**

Send one `surface,yomi` line per request to a single process, require exactly one non-empty output line per request, preserve request order by `token_index`, reject commas/newlines in individual fields, and convert exit or count mismatch to `StageFailure("accent", ...)`. Tests must use `fake_tdmelodic.py`, not Docker.

- [ ] **Step 6: Run tests and commit**

Run: `pytest tests/unit/test_mora.py tests/unit/test_accent_parser.py tests/contract/test_tdmelodic.py -q`  
Expected: PASS.

```bash
git add src/japanmfa/frontend/mora.py src/japanmfa/accent tests/unit/test_mora.py tests/unit/test_accent_parser.py tests/contract/test_tdmelodic.py tests/fixtures/bin/fake_tdmelodic.py
git commit -m "feat: derive mora-level Japanese pitch labels"
```

### Task 6: Japanese MFA G2P, Occurrence Aliases, and Locked Lexicon

**Files:**
- Create: `src/japanmfa/mfa/__init__.py`
- Create: `src/japanmfa/mfa/g2p.py`
- Create: `src/japanmfa/mfa/lexicon.py`
- Test: `tests/contract/test_mfa_g2p.py`
- Test: `tests/unit/test_locked_lexicon.py`
- Create: `tests/fixtures/bin/fake_mfa.py`

**Interfaces:**
- Produces: `MfaG2pClient.pronounce(readings: Sequence[str], work_dir: Path) -> tuple[Pronunciation, ...]`
- Produces: `LockedLexicon.build(utterance_id: str, tokens: tuple[Token, ...], pronunciations: tuple[Pronunciation, ...]) -> LockedLexicon`
- Produces: `LockedLexicon.write(corpus_dir: Path, dictionary_path: Path) -> None`

`LockedLexicon` is a frozen record containing `utterance_id`, ordered `aliases`, `transcript`, `tokens`, and `pronunciations`; all tuples have the same token count.

- [ ] **Step 1: Write the failing G2P command test**

Assert the adapter writes a UTF-8 word list of locked katakana, calls the configured MFA executable as an argv array, reads MFA dictionary output, preserves duplicate readings by input position, and rejects missing, multiple, or out-of-vocabulary pronunciations. The fake command should support the expected `mfa g2p INPUT japanese_mfa OUTPUT` shape and record argv.

- [ ] **Step 2: Implement `MfaG2pClient` with a narrow CLI compatibility seam**

Create `_build_command(input_path, output_path) -> list[str]` as the only version-specific method. Parse tab- or whitespace-separated dictionary rows into `Pronunciation(reading, phones)`. If the installed Japanese MFA version requires `--dictionary_path` or another documented option, adjust only `_build_command` and pin that version in the environment file during Task 11.

- [ ] **Step 3: Write alias/lexicon tests**

```python
def test_aliases_are_unique_per_occurrence() -> None:
    lexicon = LockedLexicon.build("speaker/001", tokens("今日 今日"), pronunciations(...))
    assert lexicon.aliases == ("jmfa_000000", "jmfa_000001")
    assert lexicon.transcript == "jmfa_000000 jmfa_000001"
    assert len(set(lexicon.aliases)) == 2
```

Also assert aliases contain only `[a-z0-9_]`, dictionary rows each have one pronunciation, and tokens/pronunciations count or reading mismatch raises `StageFailure("mfa_g2p", ...)`.

- [ ] **Step 4: Implement deterministic locked lexicon writing**

Alias numbers follow token order, not hashes. Write one corpus `.lab` file containing aliases and one dictionary line per alias. Persist a sidecar `aliases.json` mapping alias to token index, surface, reading, morae, and phones. Use atomic writes.

- [ ] **Step 5: Run tests and commit**

Run: `pytest tests/contract/test_mfa_g2p.py tests/unit/test_locked_lexicon.py -q`  
Expected: PASS.

```bash
git add src/japanmfa/mfa tests/contract/test_mfa_g2p.py tests/unit/test_locked_lexicon.py tests/fixtures/bin/fake_mfa.py
git commit -m "feat: build MFA-locked occurrence lexicons"
```

### Task 7: MFA Alignment Runner and Raw TextGrid Parsing

**Files:**
- Create: `src/japanmfa/mfa/runner.py`
- Create: `src/japanmfa/mfa/textgrid.py`
- Test: `tests/contract/test_mfa_runner.py`
- Test: `tests/unit/test_mfa_textgrid.py`
- Create: `tests/fixtures/mfa/aligned.TextGrid`
- Modify: `tests/fixtures/bin/fake_mfa.py`

**Interfaces:**
- Produces: `MfaRunner.validate(corpus_dir: Path, dictionary: Path, work_dir: Path) -> None`
- Produces: `MfaRunner.align(corpus_dir: Path, dictionary: Path, output_dir: Path, work_dir: Path) -> Path`
- Produces: `parse_mfa_textgrid(path: Path, silence_labels: frozenset[str]) -> MfaAlignment`
- `MfaAlignment` contains ordered word intervals and phone intervals with original labels and silence classification.

Define `RawMfaInterval(start, end, label, tier_name)` with `end >= start`, `MfaWord(alias, start, end)`, and `MfaPhone(label, start, end, word_alias, is_silence)`. `MfaAlignment` contains ordered `words`, positive-duration `phones`, and `diagnostic_intervals` for empty or zero-duration raw entries. A zero-duration non-silence phone is a parse failure; zero-duration empty/silence entries remain diagnostic only.

- [ ] **Step 1: Write command-construction and failure-isolation tests**

Assert validation runs before alignment and commands are equivalent to:

```text
mfa validate CORPUS DICTIONARY japanese_mfa --output_directory WORK
mfa align CORPUS DICTIONARY japanese_mfa OUTPUT --temporary_directory WORK --clean
```

The exact MFA 3.x flags must be verified with `mfa ... --help` during implementation and pinned in one builder method. Test nonzero exit, missing output TextGrid, and stderr capture.

- [ ] **Step 2: Implement the runner and pass contract tests**

Use `subprocess.run` with argv arrays and no shell. Copy stdout/stderr to deterministic log files. Never point `--clean` or temporary output at a corpus, repository root, home directory, or user-supplied broad path; require a generated utterance-owned work directory.

- [ ] **Step 3: Write raw TextGrid parsing tests**

The fixture must include word aliases, normal phones, `sil`, `sp`, `spn`, an empty interval, and a zero-duration interval. Assert:

- tier names are discovered explicitly rather than by numeric position;
- original phone labels and float boundaries are preserved;
- configured silence labels are classified as silence;
- empty/zero-duration intervals remain diagnostic records but do not shift adjacent boundaries;
- overlapping or decreasing intervals raise `StageFailure("mfa_parse", "invalid_boundaries", ...)`.

- [ ] **Step 4: Implement the parser using praatio**

Accept the standard MFA word and phone tier name variants through configuration. Convert entries into immutable domain intervals. Associate each non-silence phone with the containing word interval; reject a phone that overlaps two words or has no containing word.

- [ ] **Step 5: Run tests and commit**

Run: `pytest tests/contract/test_mfa_runner.py tests/unit/test_mfa_textgrid.py -q`  
Expected: PASS.

```bash
git add src/japanmfa/mfa/runner.py src/japanmfa/mfa/textgrid.py tests/contract/test_mfa_runner.py tests/unit/test_mfa_textgrid.py tests/fixtures/mfa tests/fixtures/bin/fake_mfa.py
git commit -m "feat: run and parse Japanese MFA alignments"
```

### Task 8: Mora-to-Phone Reconciliation and Tone Projection

**Files:**
- Create: `src/japanmfa/projection.py`
- Create: `src/japanmfa/mfa/phone_map.py`
- Create: `src/japanmfa/mfa/data/japanese_mfa_v3_phone_map.yaml`
- Test: `tests/unit/test_projection.py`
- Test: `tests/unit/test_phone_map.py`

**Interfaces:**
- Produces: `PhoneMap.load(path: Path) -> PhoneMap`
- Produces: `project_annotations(alignment: MfaAlignment, lexicon: LockedLexicon, token_morae: dict[int, tuple[Mora, ...]], phone_map: PhoneMap) -> tuple[PhoneAnnotation, ...]`

- [ ] **Step 1: Build a failing test matrix from observed Japanese MFA phones**

Cover at least simple CV, palatalized mora, `ン`, `ッ`, long vowel, devoiced-vowel spelling if emitted by the pinned model, and silence. Each test fixture states locked kana, G2P phones, aligned phones, expected mora grouping, and expected phone tone labels.

- [ ] **Step 2: Add a versioned phone-map loader with strict validation**

The YAML file names the exact model family (`japanese_mfa_v3`) and maps kana/mora patterns to expected phone groups. Reject duplicate rules, unknown rule fields, and a configured model family mismatch. Keep normalization aliases explicit; never strip IPA modifiers generically.

- [ ] **Step 3: Implement word and phone reconciliation**

Require MFA word alias order to equal `LockedLexicon.aliases`. For each word, require the ordered non-silence aligned phones to equal the locked pronunciation after only documented model-specific normalization. Map phones to mora groups with a deterministic dynamic-programming matcher; accept a result only when exactly one lowest-cost mapping exists.

- [ ] **Step 4: Implement H/L broadcast and composite labels**

```python
def labels_for_phone(morae: tuple[Mora, ...]) -> tuple[str, str]:
    kana = "|".join(m.kana for m in morae)
    tone = "|".join(cast(str, m.tone) for m in morae)
    if not kana or any(m.tone is None for m in morae):
        raise StageFailure("projection", "unlabeled_phone", "...", {})
    return kana, tone
```

For one mora mapped to multiple phones, repeat its kana and tone on each phone. For one phone mapped to multiple morae, emit ordered composites. For silence, set both labels to empty and `token_index=None`.

- [ ] **Step 5: Test ambiguity and no-invented-boundary behavior**

Add a case where one long phone maps to tones `H`, `L`; assert one annotation retains the original MFA interval and has `tone_label == "H|L"`. Add an ambiguous mapping case and assert `StageFailure("projection", "ambiguous_mora_phone_mapping", ...)`.

- [ ] **Step 6: Run tests and commit**

Run: `pytest tests/unit/test_phone_map.py tests/unit/test_projection.py -q`  
Expected: PASS.

```bash
git add src/japanmfa/projection.py src/japanmfa/mfa/phone_map.py src/japanmfa/mfa/data tests/unit/test_projection.py tests/unit/test_phone_map.py
git commit -m "feat: project mora pitch onto MFA phones"
```

### Task 9: Five-Tier TextGrid and Structured Reports

**Files:**
- Create: `src/japanmfa/output/__init__.py`
- Create: `src/japanmfa/output/textgrid.py`
- Create: `src/japanmfa/output/reports.py`
- Test: `tests/unit/test_output_textgrid.py`
- Test: `tests/unit/test_reports.py`

**Interfaces:**
- Produces: `write_five_tier_textgrid(path: Path, duration: float, original: str, kana: str, annotations: Sequence[PhoneAnnotation]) -> None`
- Produces: `validate_five_tier_textgrid(path: Path, duration: float, silence_labels: frozenset[str]) -> None`
- Produces: `write_json(path: Path, payload: Mapping[str, object]) -> None`
- Produces: `append_manifest(path: Path, outcome: UtteranceOutcome) -> None`
- Produces: `summarize(outcomes: Sequence[UtteranceOutcome]) -> dict[str, object]`

- [ ] **Step 1: Write the failing five-tier golden test**

Create annotations containing speech, silence, a multi-phone mora, and an `H|L` long phone. Assert tier names and order exactly equal:

```python
["original", "kana", "phones", "phone_kana", "phone_tone"]
```

Assert the first two tiers each contain one `[0.0, duration]` interval and the last three have byte-for-byte-equivalent serialized `xmin/xmax` values per item.

- [ ] **Step 2: Implement writer and validator**

Use praatio to write long TextGrid format. Build the three phone-level tiers from a single loop over `PhoneAnnotation` so boundaries cannot diverge. Re-open the written file and validate tier count/order, duration, monotonicity, boundary equality, silence emptiness, and non-silence completeness before atomic publication.

- [ ] **Step 3: Write report tests**

Test `aligned`/`skipped`/`failed` counts, stable reason-code grouping, Unicode JSON, JSONL append locking, and one malformed outcome rejected. Assert paths in reports are relative to input/output roots where possible and no API keys/environment secrets are serialized.

- [ ] **Step 4: Implement atomic JSON and batch reporting**

Write UTF-8 with `ensure_ascii=False`, sorted keys, and a trailing newline. Publish JSON through an adjacent temporary file and `os.replace`. Include `run_id`, tool/model versions, source type, stage durations, reason code, and trace IDs.

- [ ] **Step 5: Run tests and commit**

Run: `pytest tests/unit/test_output_textgrid.py tests/unit/test_reports.py -q`  
Expected: PASS.

```bash
git add src/japanmfa/output tests/unit/test_output_textgrid.py tests/unit/test_reports.py
git commit -m "feat: export validated five-tier alignments"
```

### Task 10: Fingerprinted Cache, Pipeline Orchestration, and CLI

**Files:**
- Create: `src/japanmfa/cache.py`
- Create: `src/japanmfa/pipeline.py`
- Create: `src/japanmfa/cli.py`
- Test: `tests/unit/test_cache.py`
- Test: `tests/integration/test_pipeline_fake_backends.py`
- Test: `tests/contract/test_cli.py`

**Interfaces:**
- Produces: `stage_fingerprint(stage: str, inputs: Mapping[str, object]) -> str`
- Produces: `StageCache.load_or_run(stage: str, fingerprint: str, producer: Callable[[Path], T]) -> T`
- Produces: `JapanMFAPipeline.run(input_root: Path, output_root: Path, overrides: Path | None) -> BatchResult`
- Produces Typer commands: `check`, `run`, `run-file`, `inspect`

- [ ] **Step 1: Write cache invalidation and atomicity tests**

Assert identical audio/text/config/model values reuse a stage, changing an override invalidates frontend and downstream stages but not audio/ASR, a producer exception never publishes a complete marker, and a stale partial directory is ignored safely.

- [ ] **Step 2: Implement canonical fingerprints and stage cache**

Hash canonical JSON containing stage name, input SHA-256 values, resolved config subset, model identifiers, and adapter versions. A completed stage directory contains `result.json` and `complete.json` with the same fingerprint. Publish by renaming a generated child of the cache parent, never by deleting an unresolved path.

- [ ] **Step 3: Write a full fake-backend pipeline test**

Use a tiny fake WAV, authoritative text, fake Qwen, fake tdmelodic, fake MFA G2P/alignment, and an MFA TextGrid fixture. Assert the pipeline writes one valid final TextGrid, four JSON/report artifacts, and an `aligned` manifest row. Add three more cases:

- forced-Japanese ASR returns `Tokyo` for missing `.txt` → `skipped`;
- malformed tdmelodic output → `failed`, batch continues;
- one MFA failure beside one valid item → one `failed`, one `aligned`.

- [ ] **Step 4: Implement stage orchestration**

Order stages as audio → source/ASR → frontend/overrides → mora/accent → G2P/lexicon → MFA → projection → output. Catch only `SkipUtterance` and `StageFailure` per utterance; unexpected exceptions become `failed` with a traceback path, then processing continues. Publish a final result only after the TextGrid validator passes.

- [ ] **Step 5: Write CLI tests with Typer's `CliRunner`**

Assert `run` refuses identical input/output roots, refuses output nested inside the input corpus, accepts absolute config/override paths, returns nonzero only for batch-level setup failure, and `inspect` prints aligned/skipped/failed counts from a manifest.

- [ ] **Step 6: Implement the four CLI commands**

`run-file` builds a temporary one-item manifest without modifying the source directory. `run` prints the final summary path and accepts an optional positive `--limit` used only to bound smoke tests after deterministic discovery. `inspect` is read-only. `check` delegates to Task 11's preflight API.

- [ ] **Step 7: Run tests and commit**

Run: `pytest tests/unit/test_cache.py tests/integration/test_pipeline_fake_backends.py tests/contract/test_cli.py -q`  
Expected: PASS.

```bash
git add src/japanmfa/cache.py src/japanmfa/pipeline.py src/japanmfa/cli.py tests/unit/test_cache.py tests/integration/test_pipeline_fake_backends.py tests/contract/test_cli.py
git commit -m "feat: orchestrate resumable JapanMFA runs"
```

### Task 11: Reproducible Environments, Preflight Checks, and User Documentation

**Files:**
- Create: `environment.yml`
- Create: `environments/mfa.yml`
- Create: `environments/asr.yml`
- Create: `tools/build_tdmelodic_image.sh`
- Create: `src/japanmfa/checks.py`
- Create: `tests/contract/test_checks.py`
- Create: `README.md`
- Create: `docs/architecture.md`
- Create: `docs/input-output.md`
- Create: `docs/reading-overrides.md`
- Create: `docs/accent-mapping.md`
- Create: `docs/limitations.md`

**Interfaces:**
- Produces: `run_preflight(config: PipelineConfig) -> PreflightReport`
- Consumes all stable public interfaces documented by Tasks 1–10.

- [ ] **Step 1: Inspect actual tool help and pin compatible versions**

Run in isolated candidate environments:

```bash
mfa version
mfa g2p --help
mfa validate --help
mfa align --help
python -c "import qwen_asr; print(getattr(qwen_asr, '__version__', 'unknown'))"
```

Record exact resolved versions in environment YAML files and update only the narrow command/construction seams from Tasks 3, 6, and 7 if actual official APIs differ. Do not weaken the domain contracts.

- [ ] **Step 2: Write failing preflight tests using fake commands**

Cover missing executable, wrong MFA major version, absent Japanese models, unwritable output/cache, Qwen CUDA unavailable with explicit CPU disallow, tdmelodic probe returning malformed output, and a fully valid setup. The report contains individual pass/fail checks and actionable commands, never secrets.

- [ ] **Step 3: Implement preflight checks**

Use bounded subprocess timeouts. Check configured executable identity/version, model path or model registry presence, output/cache writability through a temporary child file, and one deterministic tdmelodic `sy2a` probe whose unmarked reading equals the supplied yomi.

- [ ] **Step 4: Add isolated environment manifests and tdmelodic build wrapper**

Pin Python 3.11 for the orchestrator and MFA environments. Pin Python 3.12 for the Qwen3-ASR environment, following Qwen's official isolated-environment quickstart. The shell wrapper must use `set -euo pipefail`, build from a configured tdmelodic commit, tag the image deterministically, and never modify the old repository or a global Conda environment.

- [ ] **Step 5: Write operational documentation**

Document installation, model download, preflight, single-file and batch usage, five-tier semantics, override examples, reason codes, recovery, environment isolation, and explicit v1 limitations. Include the exact rule that existing `.txt` is authoritative and the exact `H|L` long-phone convention.

- [ ] **Step 6: Run tests, link checks, and commit**

Run: `pytest tests/contract/test_checks.py -q`  
Expected: PASS.  
Run: `python -m compileall -q src && git diff --check`  
Expected: exit 0.

```bash
git add environment.yml environments tools/build_tdmelodic_image.sh src/japanmfa/checks.py tests/contract/test_checks.py README.md docs
git commit -m "docs: add isolated runtime and operating guide"
```

### Task 12: Real-Model Integration and `0922jap` Acceptance

**Files:**
- Create: `tests/integration/test_real_qwen.py`
- Create: `tests/integration/test_real_tdmelodic.py`
- Create: `tests/integration/test_real_mfa.py`
- Create: `tests/integration/test_real_pipeline.py`
- Modify: `docs/limitations.md`
- Modify: `docs/test-report-0922jap.md`

**Interfaces:**
- Validates the complete public CLI and artifact contracts.
- Produces the evidence required by the specification's completion definition.

- [ ] **Step 1: Add opt-in real backend tests**

Mark tests `@pytest.mark.real_models` and skip unless explicit model paths/environment flags are set. Each test uses a bounded local fixture and asserts schema/contract behavior rather than a brittle exact transcript for arbitrary audio.

- [ ] **Step 2: Run one real utterance through each isolated backend**

Run:

```bash
pytest -m real_models tests/integration/test_real_qwen.py -v
pytest -m real_models tests/integration/test_real_tdmelodic.py -v
pytest -m real_models tests/integration/test_real_mfa.py -v
```

Expected: Qwen reports `Japanese`; tdmelodic output round-trips to the locked yomi; MFA produces word and phone tiers with the locked alias sequence.

- [ ] **Step 3: Resolve the Windows share to a read-only Linux path**

Find the existing mount corresponding to `\\RS3621\Research_TTS\Data\Raw\0922jap`. Record the resolved path and mount mode in the test report. Do not mount, remount, copy over, rename, or write into the source share without new user authorization.

- [ ] **Step 4: Run preflight and a small real end-to-end sample**

```bash
japanmfa check --config configs/default.yaml
japanmfa run --input /resolved/read-only/0922jap --output /home/user/JapanMFA/runs/0922jap-smoke --config configs/default.yaml --limit 3
pytest -m real_models tests/integration/test_real_pipeline.py -v
```

Expected: at least one supported Japanese utterance is `aligned`, its TextGrid has exactly five valid tiers, and all scanned items have a terminal status.

- [ ] **Step 5: Run the full corpus without modifying the source**

```bash
japanmfa run --input /resolved/read-only/0922jap --output /home/user/JapanMFA/runs/0922jap-full --config configs/default.yaml
japanmfa inspect /home/user/JapanMFA/runs/0922jap-full/manifest.jsonl
```

Expected: every discovered WAV is classified; the process exits normally despite item-level skips/failures.

- [ ] **Step 6: Inspect representative TextGrids and document evidence**

Select at least one simple word sequence, one long vowel, one nasal or geminate, one ASR-fallback item if present, and one skipped/failed item. Record tier names, boundary equality checks, tone coverage, screenshots or file paths, reason codes, aggregate counts, tool/model versions, elapsed time, and all newly uncovered behavior in `docs/test-report-0922jap.md` and `docs/limitations.md`.

- [ ] **Step 7: Verify the old repository and the complete new project**

Run:

```bash
git -C /home/user/JapMFA rev-parse HEAD
git -C /home/user/JapMFA status --short --branch
pytest -q
python -m compileall -q src
git diff --check
git status --short --branch
```

Expected: old HEAD remains `55208b4e10cd2f163c1d9116b0502709d41ab656`; only its two pre-existing untracked handoff files remain; all non-optional new-project tests pass; no unintended new-project changes remain after committing reports.

- [ ] **Step 8: Commit acceptance evidence**

```bash
git add tests/integration docs/limitations.md docs/test-report-0922jap.md
git commit -m "test: validate JapanMFA on Japanese corpus"
```

## Final Review and Delivery

- [ ] Invoke `superpowers:requesting-code-review` for a whole-branch review against the confirmed spec and this plan.
- [ ] Resolve review findings using `superpowers:receiving-code-review` and rerun affected tests.
- [ ] Invoke `superpowers:verification-before-completion`; rerun the full non-optional suite, real-model smoke test, five-tier validator, `git diff --check`, and old-repository integrity checks with fresh output.
- [ ] Invoke `superpowers:finishing-a-development-branch` to present integration choices.
- [ ] Push only after verification and in accordance with the user's chosen integration action; attach any created pull request to the task.

## Self-Review Record

- Spec coverage: all 22 specification sections map to Tasks 1–12 or Final Review; no uncovered requirement remains.
- Placeholder scan: no `TBD`, implementation `TODO`, “similar to,” or unspecified error-handling steps remain.
- Type consistency: `Token`, `Mora`, `Pronunciation`, `PhoneInterval`, `PhoneAnnotation`, `LockedLexicon`, `MfaAlignment`, and `UtteranceOutcome` are introduced before consumption and retain one spelling throughout.
- Review Focus: all five high-risk input classes have explicit tests in Tasks 2, 3/4, 7, and 5/8.
- External API risk is contained in `_load_model` and MFA command-builder seams; verified versions are pinned before real integration.
