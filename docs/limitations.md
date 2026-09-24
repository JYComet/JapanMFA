# v1 limitations and follow-up

The first release is intentionally Japanese-only. Latin text, unsupported
symbols, unstable readings, and non-Japanese ASR candidates are skipped rather
than sent to MFA. Japanese punctuation is retained for display but is not a
pronounced token.

Known limitations:

- The September 23 boundary repair changes speech-phone labels to
  `HH / LL / HL / LH`; these encode predicted mora accent, not measured F0.
  A phone with multiple pitch reversals fails `unsupported_tone_contour`.
- Acoustic postprocessing adapts frame RMS, noise-floor estimation, sustained
  activity detection, and silence-edge refinement from ASRMFA--Pure. It moves
  only an explicit silence/phone edge when a nearby onset or decay is measured;
  the onset search is at most 120 ms and the tail scan at most 500 ms. Internal
  MFA speech-to-speech boundaries remain unchanged. Longer misalignments need
  independent word timing evidence or a new alignment.
- Energy is not a speech classifier. Background music, breaths, very quiet
  speech and laughter can defeat these checks; a passed check establishes
  energy coverage and geometry, not correct transcription or every phone edge.
  A single recovery using lossless mora-group aliases may recover missing
  coverage. All recovered results carry an explicit manual-review flag.
- `alignment_acoustic_coverage` rejects omitted sustained energy;
  `alignment_no_activity` rejects silent/no-speech-phone candidates.
  Rejected items keep diagnostics and do not publish final artifacts.

- Sudachi defaults and tdmelodic word-level `sy2a` do not resolve every
  sentence-context pitch change. Use span-addressed overrides for homographs
  and other context-sensitive readings.
- Compounds, proper names, numeric readings, abbreviations, and repeated
  surface forms may need explicit per-occurrence overrides. Compound-word
  handling remains a planned optimization rather than a silent correction.
- The final `0922jap` run has exposed broader phone-map coverage work: item 01
  reaches MFA but fails projection on its observed phone sequence, while item
  02 exposes `i` and item 05 exposes `tɕ`, `i`, `g`, `m`, and `ɨ`. Unknown
  phones remain explicit `unknown_phone` failures. Expanding the pinned map is
  a later optimization and requires deliberate rules and tests.
- A single MFA phone can span multiple morae, so auxiliary labels are ordered
  composites and do not imply an internal acoustic boundary.
- Trailing `]` markers are now covered: `ト]` maps to `H`, and `タ[チ]` maps
  to `L,H`. A trailing `[` remains rejected as malformed output. These cases
  are covered by parser TDD tests; unrelated malformed marker forms still
  require explicit failure handling.
- Identical duplicate rows returned by MFA G2P are accepted; conflicting
  duplicate rows remain rejected. This preserves deterministic pronunciation
  selection without silently accepting disagreement.
- MFA validation is run with `--ignore_acoustics`, each utterance gets its own
  `--temporary_directory`, and `--clean` is used for the isolated validation
  workspace. These flags are operational safeguards, not a change to source
  ownership.
- Multiline TextGrid input, NFC normalization, frontend-cache isolation, and
  `mora_spans` are covered by the final review. The aligned-output audit
  contract is checked for every aligned item, and an atomic `.japanmfa.complete`
  marker is published only with the final artifacts. Cache roots that overlap
  either the source corpus or the output root are rejected before any batch
  write; these safeguards do not expand the pinned MFA phone map.
- `run` and `check` use the same configured Qwen and tdmelodic selections, and
  `resolved_config.yaml` records the effective commands for an acceptance run.
  CLI compatibility is locked to Click 8.1.8 for this environment; this is a
  reproducibility pin, not a claim of compatibility with every Click release.
- Qwen3-ASR validates or supplies text but is not a timestamp source. MFA alone
  determines final phone timing; Qwen3 Forced Aligner is not used.
- The accepted Qwen evidence is environment-deviant: it came from an isolated
  Python 3.10.20 / Torch 2.9.1+cu128 clone and requires the worktree
  `PYTHONPATH` because package metadata targets Python >=3.11. It cannot be
  reproduced verbatim from the checked-in `environments/asr.yml` target
  (Python 3.12 / Torch 2.6.0) until that environment is provisioned and
  retested. The checked-in manifest remains the intended target.
- tdmelodic requires the compatibility pins used by the real image: NumPy
  below 2 because NumPy 2 removed `np.sctypes`, and `setuptools==59.8.0` for
  Chainer compatibility.
- No automatic model download, environment creation, or global-cache cleanup
  is performed. By default the worker follows the probed CUDA availability and
  falls back to CPU; set `JAPANMFA_REQUIRE_CUDA=1` when CPU execution is not
  allowed.
- English or Japanese-English mixed utterances are outside this version and
  are skipped. Mixed-language handling is a future scope item; batch isolation
  means other utterances continue.
- Compound readings, proper names, numeric and abbreviation expansion,
  mixed-language text, and additional MFA phone aliases require dedicated
  fixtures and acceptance cases. The correct response to an uncovered case is
  an explicit failure or skip, never a silent fallback.

Task 12 real-model evidence, including the two aligned five-tier outputs and
the observed failures, is recorded in
[`docs/test-report-0922jap.md`](test-report-0922jap.md). Future additions to
this document should include the reproduction, affected artifact, and stable
reason code for every newly observed reading, mora, tdmelodic output, MFA
phone, or model-compatibility issue.
