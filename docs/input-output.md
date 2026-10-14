# Input and output contract

## Inputs

An input corpus recursively contains one lowercase `.wav` or `.ogg` per utterance and may contain a
same-stem UTF-8 `.txt`:

```text
corpus/speaker_a/001.ogg
corpus/speaker_a/001.txt
```

The relative stem (`speaker_a/001`) is the utterance ID. Input and output roots
must not be equal or nested. `run-file` copies one audio/text pair into a
temporary one-item corpus and does not modify the source directory.

An existing `.txt` is authoritative. Qwen3-ASR is still invoked with language
locked to `Japanese` to validate it and the difference is recorded. Without a
`.txt`, ASR supplies a candidate; unsupported or non-Japanese output is
skipped. Audio is native-rate trimmed/edge-normalized, then converted to the
project-owned mono PCM16/16 kHz working copy consumed by every timestamp stage.

## Six production tiers

| Tier | Intervals | Label |
|---|---|---|
| `original` | one complete-utterance interval | original text after a leading `<sp1>` marker; publication inserts `……` at unpunctuated internal sp1–sp3 gaps and `。` only for an unpunctuated real trailing pause |
| `kana` | one complete-utterance interval | locked katakana with the same publication-only punctuation and leading `<sp1>` marker |
| `words` | MFA word intervals updated at refined silence edges, plus actual positive-duration gaps | source punctuation on matching gaps; unpunctuated internal `<sp0>` extends the preceding word, while sp1–sp3 display `……` |
| `phones` | MFA intervals with bounded silence-edge refinement and canonical silence gaps | MFA phone labels; the same pause punctuation as words; unpunctuated internal `<sp0>` extends the preceding phone |
| `phone_kana` | byte-for-byte same boundaries as `phones` | mora/kana contribution, possibly `オ|ー` |
| `phone_tone` | byte-for-byte same boundaries as `phones` | `HH`, `LL`, `HL`, or `LH` for known mora tones; `??` only when every contributing mora tone is unknown; source punctuation or canonical `<sp0>`–`<sp3>` for silence |

`??` records an unavailable lexical-accent prediction; it is not an inferred pitch contour. A speech phone combining known and unknown mora tones is rejected. Outputs containing `??` declare `tone_encoding: HH_LL_HL_LH_??` and an explicit unknown-tone source/count in the JSON audit. Outputs with only known tones retain `tone_encoding: HH_LL_HL_LH`.

If MFA G2P returns multiple distinct pronunciations for one locked reading,
only candidates that map completely and uniquely to the locked morae are
written under that occurrence alias. MFA selects the acoustic sequence;
projection accepts only an exact retained candidate and records the variants
in the alias audit.

The original and kana tiers are deliberately not split by token or phone. The
words tier follows MFA word boundaries, synchronized to any refined phone
silence edge, and uses punctuation only where a real word gap exists. Unpunctuated internal sp1–sp3 gaps display `……` in all timed tiers and insert the same mark between the corresponding words in original/kana. A missing terminal mark is supplied as `。` only for a real trailing pause; the raw TXT remains unchanged. Untimed punctuation remains in original/kana and
is listed in `postprocess.json.punctuation_unplaced`. The phone and its two
auxiliary tiers follow the published, possibly refined, phone boundaries. Consecutive silence fragments are merged at publication. Pause labels and boundaries
match words across all three lower tiers, including source punctuation; every
non-silence phone must have both labels.
All three lower tiers partition the entire file, including positive-duration
canonical silence intervals and uncovered leading, internal, and trailing gaps.
The first real leading silence owner is always `<sp1>`; legacy input
silence-label configuration does not change this publication vocabulary.
`alignment.json` stores that same merged publication partition plus the full per-phone mora trace.
`postprocess.json` retains the separate acoustic intervals and their explicit/synthetic provenance. Its `publication_sp0_merges` records visual short-pause extensions and `publication_internal_ellipsis` records inserted internal marks with pause energy.
Ongoing correction evidence belongs in [the alignment issue ledger](alignment-issues.md).

`postprocess.json` stores raw/final phone intervals, integer-tick structural
issues, 15 ms short-phone issues, energy boundary edits, refined-silence
frame-BGM suspects, raw MFA word/owned-phone energy evidence, and blocked
upstream capabilities. Enabled
QC failures produce diagnostics but no final TextGrid, processed WAV,
`alignment.json`, `audio.json`, or completion marker. `audio.json` records
source/working metadata and hashes; the published WAV is byte-identical to the
MFA working input.

Per-utterance `asr.json` stores source text, cleaned ASR result, aligned text,
lexical timestamps, and punctuation gap/point or uncertain lexical-span
timestamps. The directly runnable
MFA corpus is under `mfa/corpus/`: same-stem working `.wav` and occurrence-alias
`.lab`, with `mfa/dictionary.dict`. Native Qwen timestamps normally bound MFA
crops under `mfa/segments/NNN/`, including a single-word utterance. Short
isolated spans receive limited context; sustained speech-level sound touching
another Qwen edge can add bounded context. The pipeline restores word and
phone intervals to global working-WAV time. `mfa.json` records each group's
crop, Qwen anchor, and acoustic support limit in global seconds;
`postprocess.json.timestamp_alignment` records outer-edge differences. A
difference above 0.2 seconds blocks publication unless that specific edge is
supported by acoustic context and all quality checks pass. Punctuation stays out of `.lab`.

Per-utterance JSON stores source text, ASR result, tokens, overrides, morae,
tdmelodic output, G2P/alias data, MFA diagnostics, projections, and the final
validation result. Batch `manifest.jsonl` stores one outcome per utterance;
`summary.json` groups status and reason codes. Every batch also atomically
writes `resolved_config.yaml`. It records the effective configuration,
resolved input/output/cache paths, ASR/MFA/tdmelodic models and commands,
JapanMFA/Python versions, and installed orchestrator dependency versions.
Sensitive environment values and secret-like configuration fields are redacted.
The manifest `source_type` is `txt` when an authoritative sidecar exists and
`asr` when the utterance used ASR fallback.

When an authoritative `.txt` exists, `asr.json` retains the original text and
adds `comparison` with the normalized authoritative and ASR strings, an
`equal` flag, and a `difference` object when they differ. Normalization for
this audit is NFKC, removal of CR/LF separators, and trimming surrounding
whitespace. The original text is never rewritten. If no `.txt` exists, the
comparison is marked `performed: false` with reason `no_authoritative_text`.

## Status and recovery

- `aligned`: all six tiers, acoustic checks, and required JSON artifacts validate
  (not an assertion of human-verified phone accuracy);
- `skipped`: known unsupported input, normally `unsupported_japanese_text`;
- `failed`: supported input hit a typed stage or consistency failure.

Cached stages are reused only when their fingerprint and required files match.
Delete/retry only project-owned utterance paths when recovering a corrupt stage.


## Standalone ASR batch output

`japanmfa asr-batch --input CORPUS --output NEW_DIRECTORY` always uses the
ASR transcription, even when the input has a same-stem `.txt`. The output
contains same-stem normalized `.wav` and ASR `.txt` pairs under one directory
per utterance. These pairs can be passed to `japanmfa run`. The paired `.json`
has full-sentence `kana`, `words` with Japanese surface/kana/start/end, and
separate punctuation timestamps. Word readings are derived from the full ASR
sentence with Sudachi and optional reading overrides; Qwen's Japanese text
alignment does not use kana. Output word units can merge Qwen and Sudachi units
when their boundaries cross. The root `manifest.jsonl` records transcribed,
skipped, and failed items, and `summary.json` counts them.
