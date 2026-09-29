# Architecture

JapanMFA is a new repository and a Japanese-only pipeline. The old
`/home/user/JapMFA` project is outside this repository's dependency and write
scope.

```text
.wav/.ogg + optional .txt
  -> native-rate ASRMFA trim/edge normalization -> FFmpeg mono PCM16/16 kHz working copy
  -> Qwen3-ASR (Japanese, validation or text fallback) + Qwen3 ForcedAligner lexical/derived punctuation timing
  -> SudachiPy SplitMode.B + reading overrides
  -> mora segmentation
  -> tdmelodic sy2a(surface, yomi) -> H/L
  -> Japanese MFA G2P + mappable pronunciation filter + occurrence aliases + locked dictionary
  -> Qwen-bounded speech groups + MFA v3 validate/align + timestamp audit -> final phone intervals
  -> mora-to-phone projection
  -> energy-supported silence/phone edge refinement + structural/short-phone/frame-BGM/word-energy QC
  -> six-tier TextGrid + processed WAV + JSON/manifest/summary
```

The Python 3.11 orchestrator owns discovery, validation, caching, projection,
and output. MFA runs in `japanmfa-mfa` (Python 3.11), Qwen3-ASR runs in
`japanmfa-asr` (Python 3.12), and tdmelodic is intended for a separately
versioned command/container. Data crosses boundaries using JSON, line-oriented
text, dictionaries, and TextGrid files; model imports stay out of the
orchestrator process.

## Stage contracts

- Source `.txt` is authoritative when present; Qwen3 ForcedAligner aligns that
  text, while ASR remains a Japanese-language validation signal. Missing `.txt`
  uses cleaned ASR text only after frontend checks. Punctuation timing is
  inferred from lexical gaps and retained in `asr.json`, not written to MFA `.lab`.
- Sudachi tokens keep source spans, surfaces, part of speech, and locked
  katakana. A bad override fails the utterance rather than moving to another
  occurrence.
- tdmelodic predicts accent from the locked reading but never changes it.
- MFA G2P supplies one or more phone strings for each occurrence alias after
  filtering candidates that cannot map completely and uniquely to the locked
  morae. Qwen gaps of at least 0.4 seconds separate MFA groups at locked token
  boundaries. Within continuous speech, a token boundary can split groups when
  both resulting spans have at least 0.6 seconds; shorter and zero-width
  model items join adjacent speech in that region. MFA normally uses the Qwen
  group start/end as audio crop bounds. An isolated group under 0.25 seconds
  receives limited context; sustained speech-level energy directly outside
  any group's Qwen edge can extend its crop, capped by the neighboring gap
  midpoint. The original Qwen edges remain audit anchors.
  MFA supplies phonetic boundaries inside each crop. The pipeline restores
  global times and rejects an outer MFA word edge that differs over 0.2 seconds
  from its Qwen anchor unless independent acoustic context supports that edge
  and acoustic quality checks pass. Missing timestamps fail the native
  alignment path. Postprocessing moves only an
  explicit silence/phone edge with nearby sustained energy and a confirmed
  onset or decay. It never splits an MFA phone or changes a speech-to-speech
  edge. Uncovered gaps become canonical `<sp0>`–`<sp3>` owners; sustained
  speech-level sound inside a synthetic gap blocks publication.
- Projection checks the expected phone sequence and can only annotate each
  actual MFA phone; it does not subdivide a phone.
- The BGM check scans 50 ms frames in the refined explicit silence intervals,
  using the old pipeline's global noise-floor rule. Structural and enabled QC
  failures are rejected without an MFA retry. CTC word anchors, Chinese word
  mutation, and CTC-gap BGM checks remain unsupported; Qwen lexical timestamps
  are used for MFA speech-group windows and their outer-edge audit.
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


## ASR-only batch branch

`japanmfa asr-batch` reuses audio normalization, Qwen transcription and
ForcedAligner timing, and the Japanese frontend. It exports same-stem WAV/TXT
pairs plus a JSON word/kana timeline without loading MFA, G2P, tdmelodic, or
phone projection. The ASR output text is the batch authority. Kana is derived
from full-sentence Sudachi readings; overlapping Qwen and Sudachi units are
merged before publication rather than splitting a reading across timestamps.
