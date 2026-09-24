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
| `original` | one complete-utterance interval | original text exactly as supplied after a leading `<sp1>` marker |
| `kana` | one complete-utterance interval | full locked katakana with display gaps preserved and a leading `<sp1>` marker |
| `words` | MFA word intervals updated at refined silence edges, plus actual positive-duration gaps | original Japanese token surfaces; original punctuation replaces a matching silence gap; otherwise canonical `<spN>` |
| `phones` | MFA intervals with bounded silence-edge refinement and canonical silence gaps | MFA phone labels, including `<sp0>`–`<sp3>` |
| `phone_kana` | byte-for-byte same boundaries as `phones` | mora/kana contribution, possibly `オ|ー` |
| `phone_tone` | byte-for-byte same boundaries as `phones` | exactly `HH`, `LL`, `HL`, or `LH`; canonical `<sp0>`–`<sp3>` for silence |

If MFA G2P returns multiple distinct pronunciations for one locked reading,
all candidates are written under that occurrence alias. MFA selects the acoustic
sequence; projection accepts only an exact candidate and records all variants
in the alias audit.

The original and kana tiers are deliberately not split by token or phone. The
words tier follows MFA word boundaries, synchronized to any refined phone
silence edge, and uses source punctuation only where a real word gap exists. Untimed punctuation remains in original/kana and
is listed in `postprocess.json.punctuation_unplaced`. The phone and its two
auxiliary tiers follow the published, possibly refined, phone boundaries. Silence labels
have the same canonical silence label in all three lower tiers; every
non-silence phone must have both labels.
All three lower tiers partition the entire file, including positive-duration
canonical silence intervals and uncovered leading, internal, and trailing gaps.
The first real leading silence owner is always `<sp1>`; legacy input
silence-label configuration does not change this publication vocabulary.
`alignment.json` stores that same partition plus the full per-phone mora trace.

`postprocess.json` stores raw/final phone intervals, integer-tick structural
issues, 15 ms short-phone issues, energy boundary edits, refined-silence
frame-BGM suspects, raw MFA word/owned-phone energy evidence, and blocked
upstream capabilities. Enabled
QC failures produce diagnostics but no final TextGrid, processed WAV,
`alignment.json`, `audio.json`, or completion marker. `audio.json` records
source/working metadata and hashes; the published WAV is byte-identical to the
MFA working input.

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
