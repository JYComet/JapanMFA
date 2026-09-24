# Architecture

JapanMFA is a new repository and a Japanese-only pipeline. The old
`/home/user/JapMFA` project is outside this repository's dependency and write
scope.

```text
.wav/.ogg + optional .txt
  -> native-rate ASRMFA trim/edge normalization -> FFmpeg mono PCM16/16 kHz working copy
  -> Qwen3-ASR (Japanese, validation or text fallback)
  -> SudachiPy SplitMode.B + reading overrides
  -> mora segmentation
  -> tdmelodic sy2a(surface, yomi) -> H/L
  -> Japanese MFA G2P + occurrence aliases + locked dictionary
  -> MFA v3 validate/align -> final phone intervals
  -> mora-to-phone projection
  -> immutable MFA phone projection + upstream structural/short-phone/BGM/word-energy QC
  -> six-tier TextGrid + processed WAV + JSON/manifest/summary
```

The Python 3.11 orchestrator owns discovery, validation, caching, projection,
and output. MFA runs in `japanmfa-mfa` (Python 3.11), Qwen3-ASR runs in
`japanmfa-asr` (Python 3.12), and tdmelodic is intended for a separately
versioned command/container. Data crosses boundaries using JSON, line-oriented
text, dictionaries, and TextGrid files; model imports stay out of the
orchestrator process.

## Stage contracts

- Source `.txt` is authoritative when present; ASR remains a Japanese-language
  validation signal. Missing `.txt` uses ASR text only after frontend checks.
- Sudachi tokens keep source spans, surfaces, part of speech, and locked
  katakana. A bad override fails the utterance rather than moving to another
  occurrence.
- tdmelodic predicts accent from the locked reading but never changes it.
- MFA G2P determines a single phone string for each occurrence alias. MFA
  supplies phonetic boundaries; postprocessing never moves or splits those
  boundaries. Uncovered gaps become canonical `<sp0>`–`<sp3>` owners.
- Projection checks the expected phone sequence and can only annotate each
  actual MFA phone; it does not subdivide a phone.
- Structural and enabled QC failures are rejected without boundary mutation or
  an MFA retry. CTC-timed energy refinement, Chinese word mutation, and CTC-gap
  BGM checks remain explicitly blocked because their evidence is unavailable.
- Output is published only after acoustic and six-tier structural checks pass.

Each utterance has isolated artifacts and a manifest outcome (`aligned`,
`skipped`, or `failed`). Expected `SkipUtterance`/`StageFailure` values are
recorded as reason codes and do not abort sibling utterances. Unexpected errors
are captured as a failed outcome with a diagnostic traceback path.

## Isolation and recovery

The source corpus is read-only by policy. Native-rate processed audio, MFA temporary files,
cache entries, and final output live in project-owned paths. Stage fingerprints
include source content, trim settings, implementation revision, and adapter/model
identity; atomic publication prevents partial artifacts from being accepted as
cached successes. Final output includes a same-basename processed WAV and
`audio.json` receipt whose hash matches the MFA working copy.
