# Phone contour and boundary repair: 2026-09-23

## Reproduced defects

The reported example is `角色__v_liv__v_liv_04.wav` (2.1073015873 seconds),
transcribed by Qwen3-ASR as `ははは。`. The preserved baseline is
`/home/user/JapanMFA/runs/0922jap-full-final3/`.

Its original MFA output has blank intervals at `0–0.66` and
`1.00–2.107312`, with all six speech phones between `0.66–1.00`.
The public five-tier export drops the positive-duration blank intervals.
This produces an incomplete IntervalTier partition that a viewer can render
as if the first and last phones extend to the file edges.

That export error is separate from an acoustic alignment error: normalized
audio has substantial activity around `0.04–0.45` and `0.69–0.85` seconds.
The baseline MFA alignment misses most of the earlier activity. Structural
TextGrid validity alone did not establish alignment accuracy in the previous
acceptance report.

## Diagnostic experiments

All experiments used project-owned copies and isolated MFA temporary paths.
They did not modify source WAV files. The experiments are diagnostic evidence,
not production defaults or manually verified reference alignments.

| Experiment | Observed speech-phone support | Conclusion |
| --- | --- | --- |
| Baseline single alias | `0.66–1.00` | Earlier activity omitted |
| Initial silence probability 0, silence boost 0.1, beam 100/retry 400 | `0.66–1.00` | No improvement; `final_silence_probability` was reported as unsupported |
| Crop working audio to `0.02–0.92`, same alias | Global `0.02–0.44` | Later activity omitted |
| Cropped audio, three aliases each pronounced `h a`, tokenization disabled | Global `0.02–0.44` and `0.66–0.87` | Covers both activity regions, but exact laughter-phone allocation remains unverified |
| Full audio, three aliases each pronounced `h a`, tokenization disabled | `0–0.44` and `0.66–1.00` | Covers both regions but first `h` is implausibly short (`0–0.01`) |

Diagnostic artifacts are under
`/home/user/JapanMFA/.runtime/artifacts/boundary-*-aligned/` and the matching
`boundary-*-work/` directories. An initial split-alias trial without
`--no_tokenization` produced OOV labels and is not valid alignment evidence.

## Reference provenance

The reference repository is
[ASRMFA--Pure](https://github.com/JYComet/ASRMFA--Pure/tree/c2bcdf6ef81f67aa93bf1bf5e4bb5dbfc8278c85).
Its remote `main` was verified at
`c2bcdf6ef81f67aa93bf1bf5e4bb5dbfc8278c85`.
Relevant sources are
[audio_energy.py](https://github.com/JYComet/ASRMFA--Pure/blob/c2bcdf6ef81f67aa93bf1bf5e4bb5dbfc8278c85/scripts/audio_energy.py)
and
[postprocess_textgrids.py](https://github.com/JYComet/ASRMFA--Pure/blob/c2bcdf6ef81f67aa93bf1bf5e4bb5dbfc8278c85/scripts/postprocess_textgrids.py).
Only language-independent audio/geometry concepts apply; Chinese tone,
pinyin, English-unit and transcript replacement rules are outside this repair.

## Source integrity baseline

The input remains `/mnt/Raw/0922jap`, containing five WAV files and no TXT.
SHA-256 values recorded before repair verification:

| Item suffix | SHA-256 |
| --- | --- |
| 01 | `8858c64b7ff59e37f342f26940a7e7e91cca73a80a389275f492634755064f79` |
| 02 | `c6a25cb3ef1a23f248ea9b9c7af4ac907571146be6eb699e43c49c817cc3fdca` |
| 03 | `4847e6c4948ac7c66f502f0e5ea94daa56f49825612afc769f77841624117a9e` |
| 04 | `7625a8c6404e54c7eb277682b16e9cc770e03be6b8e7c44bfe853b0b5c562a17` |
| 05 | `ae7bb16d774a6b687e0a5475e0455980091780079dfab4c7cbadd733abd4876c` |

The old `/home/user/JapMFA` repository was inspected read-only at
`55208b4e10cd2f163c1d9116b0502709d41ab656`.
After both real runs, all five source hashes still matched and the old
repository retained that HEAD and its same two pre-existing untracked handoffs.

## Runtime maintenance

The orchestrator's editable installation referenced the previously removed
worktree. Reinstalling with `pip install --no-deps -e /home/user/JapanMFA`
restored the stable main-checkout entry point. Repair verification explicitly
uses the repair worktree's `src` through `PYTHONPATH`.

## Verification

Before changes: `238 passed, 4 skipped`. After repair: `265 passed, 4 skipped`.
Existing-output real pipeline integration tests: `6 passed`.
An independent Praatio read with `includeEmptyIntervals=True` matched every
lower-tier interval and label to both `alignment.json` and
`postprocess.json.final_phones` for both published outputs. Both retain
one original interval and one kana interval. Numeric token and mora indices
are preserved, while secret fields remain redacted.

The first diagnostic run with coverage rejection but before nearby-edge
repair/recovery is at `runs/0922jap-boundary-tone-20260923`: 0 aligned,
2 `alignment_acoustic_coverage`, 3 `unknown_phone`.
It demonstrates that the new checks catch both previously accepted problems.

The authoritative repaired run is at the stable location
`/home/user/JapanMFA/runs/0922jap-boundary-tone-final-20260923`:

| Item | Outcome | Observation |
| --- | --- | --- |
| 01 | failed, `unknown_phone` | Existing phone-map coverage limitation; no final artifact |
| 02 | failed, `unknown_phone` | Existing phone-map coverage limitation; no final artifact |
| 03 | aligned | `a` refined from `0.07–0.54` to `0–0.375`, tone `LL`; explicit blank tail |
| 04 | aligned, manual review required | Lossless mora-group recovery selected; full activity coverage restored |
| 05 | failed, `unknown_phone` | Existing phone-map coverage limitation; no final artifact |

Totals: **2 aligned / 3 failed / 0 skipped**. Both published outputs have a
completion marker and zero uncovered active seconds under the documented
energy check. This is not a human gold-standard phonetic evaluation.

Item 04's complete lower-tier partition is:

| Start | End | Phone | Contour |
| ---: | ---: | --- | --- |
| 0 | 0.030 | blank | blank |
| 0.030 | 0.065 | h | LL |
| 0.065 | 0.435 | a | LL |
| 0.435 | 0.665 | blank | blank |
| 0.665 | 0.755 | h | HH |
| 0.755 | 0.785 | a | HH |
| 0.785 | 0.835 | h | HH |
| 0.835 | 0.860 | a | HH |
| 0.860 | 2.1073015873 | blank | blank |

The original attempt missed 0.39 seconds of sustained activity. The accepted
retry uses a working crop `0.015–0.875`, restores its sample-exact source
offset, and preserves the locked `h a h a h a` sequence and mora accent order.
It inserts no hand-placed internal phone boundaries. The first long `a` and
the distribution of laughter pulses still warrant listening and manual review;
energy coverage alone cannot prove that each laugh matches the ASR spelling.

`HH/LL/HL/LH` and long-phone H→L behavior are tested with deterministic
mora/phone fixtures. This corpus's two published items exercise HH and LL;
they do not independently validate long-vowel HL/LH against measured audio F0.

## Migration scope

The independent implementation adapts frame RMS, percentile noise estimation,
sustained onset/offset detection, and detection of activity in silence from
the reference code. It retains explicit silence, limits outer trims to 200 ms
and extensions to 80 ms, and pads activity by 15 ms. The new recovery attempt
uses existing mora provenance to offer MFA internal pause positions, then
checks aliases, phone identity/order, crop offsets, and acoustic coverage again.
Chinese/English token restoration, tone conversion, CTC-authority movement,
and broad word/phone shifting were not ported because their assumptions do not
hold for this Japanese-only pipeline.

The full raw and final phone sequences, all edge edits and the rejected first
attempt remain in `postprocess.json`. Predicted tdmelodic contours are not
measurements of performed pitch.
