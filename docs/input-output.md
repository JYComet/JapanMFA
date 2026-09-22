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
| `phones` | MFA output intervals | MFA phone labels, including silence |
| `phone_kana` | byte-for-byte same boundaries as `phones` | mora/kana contribution, possibly `オ|ー` |
| `phone_tone` | byte-for-byte same boundaries as `phones` | `H`, `L`, or ordered composite such as `H|L` |

The original and kana tiers are deliberately not split by token or phone. Only
the phone and its two auxiliary tiers follow MFA boundaries. Silence labels
have empty auxiliary labels; every non-silence phone must have both labels.

Per-utterance JSON stores source text, ASR result, tokens, overrides, morae,
tdmelodic output, G2P/alias data, MFA diagnostics, projections, and the final
validation result. Batch `manifest.jsonl` stores one outcome per utterance;
`summary.json` groups status and reason codes.

## Status and recovery

- `aligned`: all five tiers and required JSON artifacts validate;
- `skipped`: known unsupported input, normally `unsupported_japanese_text`;
- `failed`: supported input hit a typed stage or consistency failure.

Cached stages are reused only when their fingerprint and required files match.
Delete/retry only project-owned utterance paths when recovering a corrupt stage.
