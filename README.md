# JapanMFA

JapanMFA is a standalone, Japanese-only forced-alignment pipeline. It keeps
the source text and locked kana intact as whole-utterance tiers, obtains final
phone boundaries from Japanese MFA v3, and projects tdmelodic H/L labels onto
those MFA intervals. It is independent of `/home/user/JapMFA` and never uses
or modifies that repository.

## Install isolated runtimes

The orchestrator, MFA, Qwen3-ASR, and tdmelodic are separate runtimes:

```bash
conda env create -f environment.yml
conda env create -f environments/mfa.yml
conda env create -f environments/asr.yml
conda activate japanmfa
pip install -e .
```

The environment manifests pin the versions verified or selected for this
project. The Qwen package pin must be checked against the official Qwen3-ASR
release before creating that environment; this checkout deliberately does not
create environments or download weights.

Install models into project-owned or explicitly configured caches. MFA model
downloads are performed from the MFA environment, for example:

```bash
conda activate japanmfa-mfa
mfa model download acoustic japanese_mfa
mfa model download g2p japanese_mfa
```

The ASR model is local and is selected by `JAPANMFA_ASR_MODEL_PATH`, or by the
standard Hugging Face cache under `HF_HOME`. The default is
`Qwen/Qwen3-ASR-1.7B`; `Qwen/Qwen3-ASR-0.6B` may be configured as a fallback.
No implicit model download happens during `check` or `run`.

tdmelodic is built separately from the project-owned
[`tools/Dockerfile.tdmelodic`](tools/Dockerfile.tdmelodic). The wrapper requires
a 40-character immutable upstream commit and invokes Docker only after that
check:

```bash
TDMELODIC_COMMIT=<40-character-tdmelodic-sha> \
  tools/build_tdmelodic_image.sh
```

The resulting tag defaults to the first 12 characters of that SHA. The wrapper
requires a manually obtained official `unidic-mecab_kana-accent-2.1.2_src.zip`
archive and its expected SHA256:

```bash
export TDMELODIC_UNIDIC_ARCHIVE=/project-owned/downloads/unidic-mecab_kana-accent-2.1.2_src.zip
export TDMELODIC_UNIDIC_SHA256=<sha256-from-the-official-archive-release>
TDMELODIC_COMMIT=<40-character-tdmelodic-sha> tools/build_tdmelodic_image.sh
```

Obtain that archive once from the tdmelodic upstream distribution/release
source and record the publisher's checksum; the wrapper never downloads it.
It verifies a regular, non-symlink file, stages only the Dockerfile and archive
under a temporary context, invokes Docker, and removes that context on exit.
The build does not alter Conda, the old JapMFA repository, or the read-only
corpus.

## Check and run

Run preflight checks before a real job:

```bash
japanmfa check --config configs/default.yaml
```

The report checks bounded command probes, MFA 3.x, Japanese MFA models, the
Qwen runtime/model, tdmelodic `sy2a`, and temporary child-file writes under the
cache/output directories. Set `JAPANMFA_REQUIRE_CUDA=1` when CPU execution is
explicitly disallowed. Set `JAPANMFA_TDMELODIC_COMMAND` to an isolated
tdmelodic argv-like command and `JAPANMFA_ASR_MODEL_PATH` to a local model
directory when those are not discoverable from the defaults.

```bash
japanmfa run-file /path/to/001.wav --text /path/to/001.txt --output runs/one
japanmfa run --input /mnt/Raw/0922jap --output runs/0922jap-smoke --limit 3
japanmfa run --input /mnt/Raw/0922jap --output runs/0922jap-full
japanmfa inspect runs/0922jap-full/manifest.jsonl
```

An existing same-stem `.txt` is authoritative. Qwen3-ASR still runs in the
validation path and its Japanese result is recorded, but it never silently
rewrites that text. If `.txt` is absent, Japanese-only ASR text is a candidate
and must pass the same frontend checks. Unsupported non-Japanese utterances are
skipped with a reason code; one item failing does not stop the batch.

## Output

Each aligned utterance contains a validated five-tier Praat TextGrid and JSON
audit artifacts. The tiers are exactly:

1. `original` — original source text, one interval covering the complete audio;
2. `kana` — complete locked katakana, one interval covering the complete audio;
3. `phones` — MFA phone intervals, including silence;
4. `phone_kana` — kana projected onto the exact MFA phone intervals;
5. `phone_tone` — H/L projected onto the exact MFA phone intervals.

Only the last three tiers are split at MFA boundaries. A long phone spanning
multiple differently toned morae uses an ordered composite such as `H|L`; no
invented internal boundary is created. See [input/output](docs/input-output.md),
[architecture](docs/architecture.md), and [accent mapping](docs/accent-mapping.md).

## Recovery and diagnostics

The cache is content-fingerprinted and published atomically. Re-running the
same command reuses valid stages; changing text, overrides, model identity, or
audio invalidates downstream stages. Remove only the affected utterance's
project-owned output/cache when recovery requires it. Do not recursively clean
the source corpus, the old JapMFA repository, or a global environment.

Reading overrides, reason codes, unsupported cases, and compound-word follow-up
work are documented in [reading overrides](docs/reading-overrides.md) and
[limitations](docs/limitations.md). Real `0922jap` evidence belongs in the
[Task 12 template](docs/test-report-0922jap.md); the template contains no fake
results.

## Status, reason codes, and recovery actions

`check` prints one result per probe and exits 1 if any probe is not OK. `run`
always isolates an utterance: `aligned` means all five tiers validated,
`skipped` means the input is outside the Japanese v1 scope, and `failed` means
a supported item hit a typed stage/consistency error. Actions below are
operator guidance only; the pipeline never downloads, guesses a reading, or
silently retries by changing the source.

| status/check | reason codes | operator action |
|---|---|---|
| preflight pass | `ok`, `not_required` | Continue only when the report overall is OK. |
| preflight runtime/command | `executable_missing`, `runtime_unavailable`, `command_failed`, `command_timeout`, `cuda_probe_failed`, `cuda_unavailable` | Activate the named isolated runtime, verify the configured argv and GPU policy, then rerun `japanmfa check`. |
| preflight MFA version/model | `mfa_version_unparseable`, `mfa_version_incompatible`, `model_unavailable` | Use MFA 3.x and install/register the configured Japanese acoustic and G2P models. |
| preflight tdmelodic/path | `probe_malformed`, `path_not_writable` | Verify strict `sy2a(surface,yomi)` output and choose writable project-owned paths. |
| skipped input | `unsupported_japanese_text`, `non_japanese_language`, `unsupported_language` | Keep the skip, supply Japanese text/audio, or document it as out of scope; no output TextGrid is published. |
| discovery/text | `symlink_audio`, `duplicate_utterance_id`, `invalid_utf8` | Fix the corpus entry or text encoding; do not modify the source through the pipeline. |
| audio/cache | `destination_directory_failed`, `partial_cleanup_failed`, `ffmpeg_failed`, `output_stat_failed`, `empty_output`, `atomic_replace_failed`, `duration_unavailable`, `cache_artifact_missing` | Check source readability, FFmpeg, project-owned work/cache paths, and retry the affected item. |
| ASR | `audio_path_not_absolute`, `duplicate_audio_path`, `worker_start_failed`, `worker_failed`, `malformed_response`, `invalid_response`, `result_coverage_mismatch`, `unavailable` | Verify the isolated Qwen worker protocol/model; existing `.txt` remains authoritative. |
| frontend/overrides | `sudachi_unavailable`, `sudachi_dictionary_unavailable`, `tokenization_failed`, `malformed_morpheme`, `token_span_mismatch`, `invalid_override`, `duplicate_override`, `overlapping_overrides`, `override_surface_mismatch`, `invalid_override_kana`, `override_requires_complete_token` | Install/use the declared Sudachi runtime or correct the exact span/surface/kana override. |
| accent/tdmelodic | `invalid_request`, `command_start_failed`, `command_failed`, `output_count_mismatch`, `empty_output`, `malformed_output`, `mora_count_mismatch`, `reading_mismatch`, `output_coverage_mismatch` | Verify one output per token, balanced legal brackets, and exact locked-reading round-trip. |
| MFA G2P/lexicon | `invalid_reading`, `work_directory_failed`, `input_write_failed`, `output_read_failed`, `malformed_output`, `multiple_pronunciations`, `out_of_vocabulary`, `missing_pronunciation`, `invalid_utterance_id`, `count_mismatch`, `empty_pronunciation`, `artifact_write_failed` | Inspect the isolated MFA G2P command/model and regenerate only the affected project-owned artifacts. |
| MFA execution/parser | `path_ownership_invalid`, `output_directory_failed`, `work_directory_failed`, `command_start_failed`, `command_timeout`, `command_failed`, `log_write_failed`, `missing_output`, `multiple_outputs`, `malformed_textgrid`, `textgrid_read_failed`, `missing_tier`, `ambiguous_tier`, `invalid_boundaries`, `zero_duration_phone`, `phone_word_overlap`, `phone_not_contained` | Keep corpus/work/output roots disjoint and owned; inspect preserved logs and rerun after fixing MFA output. |
| phone-map/projection | `phone_map_read_failed`, `invalid_phone_map`, `unknown_field`, `model_family_mismatch`, `invalid_normalizations`, `invalid_rules`, `invalid_rule`, `unknown_rule_field`, `duplicate_rule`, `unknown_phone`, `mora_phone_mapping`, `ambiguous_mora_phone_mapping`, `mora_coverage_mismatch`, `mora_reading_mismatch`, `word_alias_mismatch`, `phone_sequence_mismatch`, `unmapped_phone`, `cross_token_mapping`, `unlabeled_phone` | Do not guess a mapping; use the pinned Japanese MFA v3 map and preserve the diagnostic for a deliberate map/override fix. |
| unexpected failure | `unexpected_exception` | Inspect the per-item traceback path and report a reproducible case; sibling items continue. |

The exact JSON reason code is the stable value to use in batch summaries and
follow-up reports. A failed or skipped item never receives a partial final
TextGrid.
