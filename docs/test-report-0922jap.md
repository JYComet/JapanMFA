# 0922jap Task 12 preflight gate report

Date: **2026-09-22**

This is a real, read-only preflight report. The gate failed before any corpus
transcription, MFA alignment, or five-tier output could be run. No alignment
result is claimed by this report.

## Corpus and safety boundary

- Source resolved from `\\RS3621\Research_TTS\Data\Raw\0922jap` to
  `/mnt/Raw/0922jap`.
- The source was readable and contained **5 WAV files and 0 TXT files** at the
  time of the check.
- The source was treated as read-only; the check did not write to it.
- Temporary output and cache locations were writable.

## Preflight results

| check | result | evidence / reason |
|---|---|---|
| MFA version/help | PASS | `/home/user/miniconda3/envs/mfa-dev/bin/mfa`; version `3.3.9` |
| MFA Japanese acoustic model registered | FAIL | `model_unavailable` |
| MFA Japanese G2P model registered | FAIL | `model_unavailable` |
| Qwen3-ASR runtime | PASS | Runtime probe passed after the 30-second timeout handling fix |
| Qwen3-ASR model cache | PASS | `Qwen3-ASR-1.7B` cache is present |
| CUDA requirement | NOT REQUIRED | The preflight policy does not require CUDA for the gate |
| tdmelodic executable/image | FAIL | `executable_missing` |
| Temporary output/cache writeability | PASS | Temporary locations accepted writes |
| Overall preflight gate | **FAIL** | Required Japanese MFA and tdmelodic artifacts are unavailable |

Additional read-only artifact evidence:

- `/home/user/ja-en-task-artifacts/japanese_mfa-v3.0.0.zip` exists and is
  `92,191,596` bytes. Acoustic model inspection exited `0`, but the model is
  not registered in the target MFA environment.
- `/home/user/ja-en-task-artifacts/japanese_mfa-v3.0.0.dict` exists and is
  `21,264,022` bytes. Its presence does not provide a registered G2P model.
- No Japanese G2P ZIP was found locally.
- No `SudachiPy` was found in the base, ASR, or `mfa-dev` environments.
  An older independent `frontend-venv` has `SudachiPy`, but lacks PyYAML and
  the complete target environment; it is not used as this project's runtime.
- The ASR environment reports Python `3.10.20`, `torch 2.9.1+cu128`, and
  CUDA available; the Qwen3-ASR version is unknown. The target Python 3.12
  ASR environment has not been provisioned.
- No tdmelodic executable or image and no UniDic 2.1.2 archive were found.

## Checks performed and reproducible commands

The following bounded probes were actually executed for the gate. They are
shown with their full executable paths; no install, download, Docker build, or
source-corpus write was performed:

```text
/home/user/miniconda3/envs/mfa-dev/bin/mfa version
/home/user/miniconda3/envs/mfa-dev/bin/mfa g2p --help
/home/user/miniconda3/envs/mfa-dev/bin/mfa validate --help
/home/user/miniconda3/envs/mfa-dev/bin/mfa align --help
/home/user/miniconda3/envs/asr/bin/python -c "import qwen_asr; print(getattr(qwen_asr, '__version__', 'unknown'))"
/home/user/miniconda3/envs/mfa-dev/bin/mfa model inspect acoustic /home/user/ja-en-task-artifacts/japanese_mfa-v3.0.0.zip
```

The acoustic archive inspection exited `0`; this inspected archive is still
not registered in the target MFA environment. The G2P registration check
remained `model_unavailable` because no local Japanese G2P ZIP was found.

The remaining inventory, environment, and writeability results came from
shell read-only inspections. The reproducible inspections actually used were:

```text
conda env list
find /mnt/Raw/0922jap -maxdepth 1 -type f -o -type d 2>/dev/null | head -20
find /home/user -maxdepth 4 -type d \( -iname '*japanmfa*' -o -iname '*qwen3*' -o -iname '*mfa*' -o -iname '*tdmelodic*' \) 2>/dev/null | head -100
find /home/user -maxdepth 5 -type d -iname '*tdmelodic*' 2>/dev/null | head -50
find /home/user/.cache/huggingface/hub/models--Qwen--Qwen3-ASR-1.7B -maxdepth 2 -type f -o -type l 2>/dev/null | head -20
conda run -n mfa-dev mfa model list acoustic
conda run -n mfa-dev mfa model list g2p
conda run -n mfa-dev python --version
conda run -n asr python --version
conda run -n asr python -c "import importlib.util; print('qwen_asr', bool(importlib.util.find_spec('qwen_asr'))); print('torch', bool(importlib.util.find_spec('torch')))"
docker images --format '{{.Repository}}:{{.Tag}} {{.ID}}' | rg -i 'tdmelodic|japan|mfa|qwen'
```

These commands only enumerated existing files, registered models, or runtime
metadata. They did not install packages, create environments, download
artifacts, or modify the source corpus.

The Qwen runtime probe initially exceeded its timeout; after the 30-second
timeout handling fix it passed. This is a runtime check only, not an ASR
transcription of the corpus.

## Task 12 execution status

| status | count | reason codes / evidence |
|---|---:|---|
| aligned | NOT RUN | `preflight_gate_failed` |
| skipped | NOT RUN | no corpus transcription was started |
| failed | NOT RUN | no per-item pipeline execution was started |

The following remain explicitly **NOT RUN**:

- `japanmfa` pipeline execution;
- ASR transcription of the 5-WAV corpus;
- MFA alignment;
- five-tier TextGrid validation;
- status/reason-code counts from a corpus run;
- representative output files or screenshots.

Therefore the following five-tier assertions are also **NOT RUN**, not
successful results:

- `original` and `kana` whole-utterance intervals;
- identical MFA boundaries for `phones`, `phone_kana`, and `phone_tone`;
- kana and tone labels for non-silence phones;
- ordered labels such as `H|L` for mixed-tone long phones.

## Recovery authorization and actions

The gate can be rerun only after the following environment changes are
authorized and completed:

1. Provision an isolated orchestrator environment containing SudachiPy.
2. Obtain/register the Japanese G2P model. Optionally register the existing
   Japanese acoustic model and dictionary copies above without modifying the
   old repository or its environments.
3. Obtain the UniDic 2.1.2 archive and an immutable tdmelodic commit, then
   build or provide the tdmelodic image/executable.
4. Provision the target Qwen Python 3.12 environment, or explicitly approve
   the documented Python 3.10 deviation for the existing ASR environment.
5. Rerun the preflight, then a smoke run, then the full `/mnt/Raw/0922jap`
   corpus and record real per-item counts and five-tier validation results.

No downloads, installations, environment creation, or Docker builds were
performed during this gate.

## Uncovered cases and follow-up

Corpus-level behavior for compounds, reading overrides, symbols, long vowels,
devoiced phones, ASR fallback items, and model-specific output remains
**TBD/NOT RUN** until the gate passes. These cases must be recorded from the
first real smoke/full-corpus run rather than inferred from this preflight.
