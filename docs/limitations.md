# v1 limitations and follow-up

The first release is intentionally Japanese-only. Latin text, unsupported
symbols, unstable readings, and non-Japanese ASR candidates are skipped rather
than sent to MFA. Japanese punctuation is retained for display but is not a
pronounced token.

Known limitations:

- Sudachi defaults and tdmelodic word-level `sy2a` do not resolve every
  sentence-context pitch change. Use span-addressed overrides for homographs.
- Compounds, proper names, numeric readings, abbreviations, and repeated
  surface forms may need explicit per-occurrence overrides. Compound-word
  behavior is a planned optimization item, not silently corrected in v1.
- The versioned phone map is tied to Japanese MFA v3. New/devoiced phones or
  model-specific aliases must be added deliberately; unknown phones fail.
- A single MFA phone can span multiple morae, so auxiliary labels are ordered
  composites and do not imply an internal acoustic boundary.
- Qwen3-ASR validates existing text but is not a timestamp source. MFA alone
  determines final phone timing; Qwen3 Forced Aligner is not used.
- No automatic model download, environment creation, or global-cache cleanup is
  performed. GPU/CPU policy must be explicit through preflight configuration.
- English or Japanese-English mixed utterances are outside this version and
  are skipped. Batch isolation means other utterances continue.
- Real Japanese MFA model, tdmelodic, Sudachi, Qwen, and `0922jap` acceptance
  results must be recorded by Task 12; this document must not claim them from
  fake tests.

Every newly observed reading, mora, tdmelodic output, MFA phone, or model
compatibility issue belongs here with its reproduction and a reason code. The
correct response to an uncovered case is an explicit failure or skip, never a
silent fallback.
