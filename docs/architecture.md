# Architecture

JapanMFA is a new repository and a Japanese-only pipeline. The old
`/home/user/JapMFA` project is outside this repository's dependency and write
scope.

```text
.wav + optional .txt
  -> FFmpeg working copy / audio metadata
  -> Qwen3-ASR (Japanese, validation or text fallback)
  -> SudachiPy SplitMode.B + reading overrides
  -> mora segmentation
  -> tdmelodic sy2a(surface, yomi) -> H/L
  -> Japanese MFA G2P + occurrence aliases + locked dictionary
  -> MFA v3 validate/align -> final phone intervals
  -> mora-to-phone projection
  -> acoustic coverage / bounded edge refinement / one optional MFA retry
  -> five-tier TextGrid + JSON/manifest/summary
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
  supplies phonetic boundaries; acoustic refinement can change only the two
  outer speech edges, recording every change and preserving internal boundaries.
- Projection checks the expected phone sequence and can only annotate each
  actual MFA phone; it does not subdivide a phone.
- A rejected coverage check may trigger one lossless mora-group MFA retry.
  Long phones are never split, source-time offsets are restored, and the full
  ordered phone sequence must remain identical.
- Output is published only after acoustic and five-tier structural checks pass.

Each utterance has isolated artifacts and a manifest outcome (`aligned`,
`skipped`, or `failed`). Expected `SkipUtterance`/`StageFailure` values are
recorded as reason codes and do not abort sibling utterances. Unexpected errors
are captured as a failed outcome with a diagnostic traceback path.

## Isolation and recovery

The source corpus is read-only by policy. Working audio, MFA temporary files,
cache entries, and final output live in project-owned paths. Stage fingerprints
include content and adapter/model identity; atomic publication prevents partial
artifacts from being accepted as cached successes.
