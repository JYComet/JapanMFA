# Input and output contract

## Inputs

An input corpus recursively contains one `.wav` per utterance and may contain a
same-stem UTF-8 `.txt`:

```text
corpus/speaker_a/001.wav
corpus/speaker_a/001.txt
```

The relative stem (`speaker_a/001`) is the utterance ID. Input and output roots
must not be equal or nested. `run-file` copies one audio/text pair into a
temporary one-item corpus and does not modify the source directory.

An existing `.txt` is authoritative. Qwen3-ASR is still invoked with language
locked to `Japanese` to validate it and the difference is recorded. Without a
`.txt`, ASR supplies a candidate; unsupported or non-Japanese output is
skipped. Audio normalization uses a project-owned working copy.

## Five tiers

| Tier | Intervals | Label |
|---|---|---|
| `original` | one complete-utterance interval | original text exactly as supplied |
| `kana` | one complete-utterance interval | full locked katakana, with display gaps preserved |
| `phones` | MFA intervals plus audited outer-edge refinement and explicit silence | MFA phone labels, including silence |
| `phone_kana` | byte-for-byte same boundaries as `phones` | mora/kana contribution, possibly `オ|ー` |
| `phone_tone` | byte-for-byte same boundaries as `phones` | exactly `HH`, `LL`, `HL`, or `LH`; blank for silence |

The original and kana tiers are deliberately not split by token or phone. Only
the phone and its two auxiliary tiers follow MFA boundaries. Silence labels
have empty auxiliary labels; every non-silence phone must have both labels.
All three lower tiers partition the entire file, including positive-duration
blank MFA intervals and uncovered leading, internal, and trailing gaps.
`alignment.json` stores that same partition plus the full per-phone mora trace.

`postprocess.json` stores the raw and final phone intervals, sample-rounding
corrections, energy thresholds, bounded outer-edge edits, and acoustic coverage
checks. A failed check is a failed utterance with diagnostics but no final
TextGrid, `alignment.json`, or completion marker. A single recovery attempt can
split occurrence aliases into lossless mora groups and rerun MFA on a cropped
working copy; the original phone order and source-time offset are verified.
`recovery.accepted` identifies a selected recovery, and
`recovery.requires_manual_review` flags its residual uncertainty.

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

- `aligned`: all five tiers, acoustic checks, and required JSON artifacts validate
  (not an assertion of human-verified phone accuracy);
- `skipped`: known unsupported input, normally `unsupported_japanese_text`;
- `failed`: supported input hit a typed stage or consistency failure.

Cached stages are reused only when their fingerprint and required files match.
Delete/retry only project-owned utterance paths when recovering a corrupt stage.
