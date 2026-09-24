> Preliminary implementation report. Final seven-OGG reference/no-reference results: [2026-09-24 report](test-report-upstream-postprocess-20260924.md).

# Upstream Japanese postprocess port — 2026-09-23

Source authority: `/home/user/JapMFA`, revision
`c2bcdf6ef81f67aa93bf1bf5e4bb5dbfc8278c85`, read with `git show`; immutable
audio authority: `/mnt/Raw/0922jap`. No source, old-repository, or existing-run
files were written.

The implementation uses the pinned native-rate functions from
`scripts/trim_silence_batch.py` (trim before edge normalization), then FFmpeg
mono PCM16/16 kHz. MFA receives `--dither 0.0` on every align path. Phone edges
are immutable; postprocess receipts separate structural, 15 ms short-phone,
explicit-MFA-silence BGM, raw-word energy, and blocked-capability evidence.

## Verification

```text
PYTHONPATH=src .../orchestrator/bin/python -m pytest -q
287 passed, 4 skipped
```

Focused audio/config/MFA/postprocess/output/pipeline/ledger tests: 39 passed;
the full suite includes the paired-audio publication, punctuation grouping,
legacy canonical-label, serialized-tick, and Japanese alias energy fixtures.
in the final focused slice.
`git diff --check` passed. A fresh five-WAV model run and actual MFA MFCC log
inspection remain root-owned verification; this report does not claim those
outcomes or claim all ASRMFA postprocessing is portable.

Native-rate parity probe (read-only `/mnt/Raw/0922jap`, frames before/after
trim/edge): `01 272679/262536/261580`, `02 63116/57824/58916`,
`03 71306/65132/66224`, `04 92932/84112/84180`, `05 90227/80525/81617`.

Explicitly blocked: timed CTC lexical/punctuation energy refinement, CTC-gap
BGM fallback, Chinese short-word boundary mutation, and silence/epsilon merge
that would delete MFA phone ownership. These are reported, not approximated.
