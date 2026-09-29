# 0922jap timestamp-guided MFA review (2026-09-28)

> 本文记录原生 ForcedAligner 检查点安装前的历史对照。检查点安装后的完整重跑与最终结果见 `docs/test-report-native-qwen-0922jap-20260928.md`。

## Scope and reproduction

The requested Windows share `\\RS3621\Research\_TTS\Data\Raw\0922jap` is mounted here as `/mnt/Raw/0922jap`. It contains seven `.ogg`/`.txt` pairs (0050 through 0110). The source was read only. The full diagnostic output is `runs/0922jap-timed-full-saved-evidence-20260928/`, especially `manifest.jsonl`, `summary.json`, and each item's `asr.json`, `mfa.json`, and `postprocess.json`.

A fresh live Qwen run was attempted, but the configured native `Qwen/Qwen3-ForcedAligner-0.6B` checkpoint has no local snapshot. After supplying the worktree `PYTHONPATH` to the isolated ASR worker, model loading could not reach Hugging Face. The seven-item rerun therefore injected the previously captured Qwen reference-text lexical timestamps from `runs/asr-batch-0922jap-20260924/alignment_comparison.json`, then used the real source audio, frontend, tdmelodic container, Japanese MFA v3 G2P/acoustic models, projection, and output QC. This validates the pipeline's consumption of those timestamps, not a fresh inference by the ForcedAligner in the current environment.

## Defect and correction

The previous main pipeline saved Qwen lexical timestamps in `asr.json` but fed MFA the full working WAV and an untimed occurrence-alias `.lab`. Thus the timestamps did not constrain MFA and a plausible TextGrid could be shifted into music or silence. A previous 0060 whole-file MFA placed `世界` at 1.22–1.44 s against Qwen's 0.48–1.20 s. The BGM check then saw the true speech region as unowned energy.

At the time of this historical run, the pipeline checked that Qwen lexical text, source text, and locked token surfaces covered the same lexical sequence. A gap of at least 0.4 s at a token boundary made a separate MFA crop: Qwen speech span plus up to 0.2 s context, bounded by the gap midpoint. It ran MFA on each crop, restored global timestamps, and rejected a group's outer MFA word edge if it differed from the Qwen anchor by more than 0.2 s. Final phone edges remained MFA-derived; no duration was fabricated to match Qwen. A single group or unsplittable lexical stream then used whole-utterance MFA; reliable outer Qwen anchors were audited even without a crop. The audit checked group outer edges, not every internal Qwen word. The subsequent native-checkpoint and acoustic-context implementation changed these crop rules; see `docs/test-report-acoustic-context-0922jap-20260928.md`.

Two adjacent upstream issues were found while reaching MFA. tdmelodic's `ネ]ツ]` has a redundant terminal fall; the parser now accepts that terminal form while still rejecting conflicting interior events. MFA G2P may return variants that cannot assign every phone to the locked morae (0090 `カンキ` included a candidate lacking an owned nasal); such variants are filtered before lexicon construction, while compatible variants remain. Exact observed MFA v3 phones for the tested readings were added to the pinned map.

## Seven-item result

| Item | Outcome | Evidence and interpretation |
|---|---|---|
| 0050 | `reading_mismatch` | Locked `ウゥ` is returned by tdmelodic as `ウ]ウ`; its pitch fall lies inside one locked mora. The pipeline correctly refuses to invent an H/L assignment. |
| 0060 | `timestamp_mfa_disagreement` | Two Qwen-bounded MFA groups. The second ends at 2.56 s versus Qwen 2.88 s, a −0.32 s drift. The original `bgm_suspect` diagnosis is retained as `acoustic_reason_code`. A direct whole-WAV MFA probe placed `世界` at 1.22–1.44 s; a timestamp crop moved it to 0.52–1.23 s, close to Qwen's 0.48–1.20 s. |
| 0070 | `reading_mismatch` | Locked `テルゥ` and `アゥ` become `テ[ルウ` and `ア]ウ` in tdmelodic. The model expands small vowels into extra morae, so the current locked-mora H/L contract cannot safely consume the output. |
| 0080 | `phone_in_silence` | The trailing MFA `/e/` at 1.11–1.14 s has RMS about 0.000134 against the 0.00214 activity threshold; Qwen's reference word ends at 0.88 s. The acoustic rejection is warranted, and there is no safe timestamp split within this utterance. |
| 0090 | `timestamp_mfa_disagreement` | After the parser, pronunciation, and phone-map fixes, MFA reaches postprocessing. The second group's first MFA word starts at 2.61 s versus Qwen 2.08 s, a +0.53 s drift. The original `bgm_suspect` remains recorded. |
| 0100 | `reading_mismatch` | Locked `ハァ` becomes tdmelodic `ハ]ア`; the fall is inside a locked mora. This requires an explicit accent/reading representation choice. |
| 0110 | `aligned` | Two MFA groups; the timestamp audit has no issues, and the final six-tier output is published. |

Summary: one aligned, six failed (three `reading_mismatch`, two `timestamp_mfa_disagreement`, one `phone_in_silence`). These failures are explicit quality gates, not successful alignments. The three reading mismatches need a separate, reviewed representation for pitch changes inside contracted small-vowel morae; changing the locked reading automatically would alter the pronunciation contract. The two timing disagreements need better audio/model evidence or human review before publication. A live seven-item acceptance run still requires the native ForcedAligner checkpoint in the configured ASR environment.
