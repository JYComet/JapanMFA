# 0922jap MFA dither correction and replay (2026-09-28)

## Inputs and limits

The seven paired OGG/TXT files in `/mnt/Raw/0922jap` were read without changing the share. The final isolated output is `runs/0922jap-dither1-final-20260928/`. It contains each item's original MFA TextGrid, `mfa.json`, `postprocess.json`, `manifest.jsonl`, `summary.json`, and `resolved_config.yaml`. Rejected items have diagnostic artifacts but no published final TextGrid.

The local native Qwen3 ForcedAligner checkpoint is unavailable. This replay used reference-text lexical timestamps previously captured in `runs/asr-batch-0922jap-20260924/alignment_comparison.json`, injected through the existing pipeline ASR interface. Audio preprocessing, tdmelodic, Japanese MFA G2P, MFA acoustic alignment, projection, and quality checks ran on the real inputs. The result is **not** a fresh live Qwen inference or a human-verified phone alignment.

## Changes and checks

- `MFAConfig` and `MfaRunner` now default to `dither=1.0`, matching the installed Japanese MFA v3 acoustic model metadata. `configs/default.yaml` states that value explicitly. The final resolved config and 15 MFCC segment logs confirm actual `dither: 1.0` and 16 kHz feature extraction.
- `configs/0922jap-reading-overrides.yaml` locks the observed contextual reading `空い → スイ` for 0110 and expands expressive small-vowel spellings for 0050, 0070, and 0100 without altering source TXT. All spans and surfaces were validated against the real seven-item corpus. The expanded readings were checked with real tdmelodic and MFA G2P.
- The Japanese MFA v3 phone map now assigns the observed `ハア → h aː` candidate across both morae. A red/green projection test covers its `HH` and `HL` phone-tone labels.
- The real MFA integration test now treats explicit silence intervals as unowned by a word; the emitted speech phones must still belong to the locked alias.

## Final seven-item result

| Item | Result | Remaining evidence |
|---|---|---|
| 0050 | rejected: `timestamp_mfa_disagreement` | MFA word 0.50–1.36 s; saved Qwen anchor 0.00–1.92 s. |
| 0060 | aligned | MFA/Qwen outer-edge audit and acoustic checks pass. |
| 0070 | rejected: `timestamp_mfa_disagreement` | Segment edges differ by −1.15 s and +1.55 s; one BGM/energy suspect also remains. |
| 0080 | rejected: `timestamp_mfa_disagreement` | MFA word ends 1.13 s, saved Qwen anchor 0.88 s; trailing phones still need acoustic review. |
| 0090 | rejected: `timestamp_mfa_disagreement` | Second group starts 2.78 s, saved Qwen anchor 2.08 s; one BGM/energy suspect also remains. |
| 0100 | aligned | Expanded `ハア`/`h aː` maps to both morae; outer-edge and acoustic checks pass. |
| 0110 | aligned | Locked `空い` reading is `スイ`; outer-edge and acoustic checks pass. |

`summary.json`: **3 aligned, 4 failed, 0 skipped**. In the earlier dither-0 timestamp replay, only 0110 aligned; 0060 and 0100 are new passing items. This comparison mixes the dither correction with the source-specific reading and phone-map fixes; the earlier isolated 0060/0080 dither experiment remains the single-variable evidence for the feature setting.

## Verification and unresolved work

- Non-real-model suite: `354 passed, 15 deselected`.
- Real Japanese MFA G2P/alignment integration: `1 passed`.
- `git diff --check`: no whitespace errors.
- The final batch's `summary.json`, all seven `postprocess.json` files, resolved `dither=1.0`, and completion markers for the three aligned outputs were checked.

The four rejected items require independent word/phone time evidence or reviewed source transcription and pronunciation before release. The saved Qwen anchors and MFA boundaries disagree; the current evidence does not establish which one is correct for every edge. Do not raise the 0.2 s drift threshold or stretch phones to count these items as passed. Even the three aligned items still need human boundary review before they can be claimed accurate at phone level.
