# 0922jap Task 12 real-model acceptance report

Recorded: **2026-09-23 UTC** for the `0922jap` corpus.

Task 12 completed a real-model preflight, discovery smoke/full runs, and an
authoritative final five-item corpus run. The preflight passed all 10 checks.
The authoritative run produced two aligned items and three failed items; no
item was skipped, and no source file was written. The earlier smoke/full
results remain below as discovery history, not as the final acceptance result.

## Corpus and source safety

- The source UNC `\\RS3621\Research_TTS\Data\Raw\0922jap` resolves to
  `/mnt/Raw/0922jap`.
- The CIFS mount reports `rw`. The application nevertheless treats the
  resolved source as source-only: corpus discovery and audio reads use the
  source, while work, cache, and output are project-owned paths. No source
  write, rename, copy-over, or delete was performed.
- The read-only inventory contains 5 `.wav` files and 0 `.txt` files. The
  five runs therefore use the Qwen result as the authoritative text input.
- The authoritative acceptance output is under `runs/0922jap-full-final2/`;
  discovery outputs are under `runs/0922jap-smoke2/` and
  `runs/0922jap-full/`. Runtime state and caches are under
  `/home/user/JapanMFA/.runtime`.

## Runtime and artifact provenance

| component | evidence |
|---|---|
| Orchestrator | `/home/user/JapanMFA/.runtime/envs/orchestrator`, Python 3.11.16, `japanmfa` 0.1.0 |
| Qwen3-ASR | Isolated clone at `/home/user/JapanMFA/.runtime/envs/asr`, Python 3.10.20, `qwen-asr` 0.0.6, `torch` 2.9.1+cu128, CUDA available (`True`). The clone requires the worktree `PYTHONPATH` because its package metadata targets Python >=3.11. |
| MFA | Isolated Python 3.11.15 runtime, MFA 3.3.9, spaCy 3.8.7, SudachiPy 0.6.10, `sudachidict-core` 20260723. |
| tdmelodic | Commit `e7fdb63f85bbdd130daf1e846c49f87f23df552f`, image `japanmfa-tdmelodic:e7fdb63f85bb`, NumPy 1.26.4, Chainer 7.8.1, tdmelodic 1.0.0. |
| UniDic | Recorded SHA-256 `70793cac...4591`. |
| Japanese MFA G2P | Recorded SHA-256 `02b575...9197`. |

The accepted Qwen evidence is environment-deviant. It was produced by the
Python 3.10.20 / Torch 2.9.1+cu128 clone above and cannot be reproduced
verbatim from the checked-in ASR manifest (`environments/asr.yml`, Python 3.12
and Torch 2.6.0) until that target environment is provisioned and retested.
The checked-in manifest remains the intended target; the current clone's
worktree `PYTHONPATH` is an execution prerequisite for the recorded evidence.

The tdmelodic Docker build exposed and fixed two compatibility problems before
the real run: NumPy 2 no longer provides `np.sctypes`, and newer setuptools is
incompatible with the Chainer build. The image now pins NumPy below 2 and
`setuptools==59.8.0`.

Three TDD changes were included before the authoritative rerun: trailing `]`
markers are accepted (`ト]` maps to `H`, and `タ[チ]` maps to `L,H`), trailing
`[` remains rejected, identical duplicate MFA G2P rows are accepted while
conflicting rows fail, and MFA validation uses `--ignore_acoustics`,
per-utterance `--temporary_directory`, and `--clean`.

## Preflight

Command: `japanmfa check --config /tmp/japanmfa-real-config.yaml`.

`/tmp/japanmfa-real-config.yaml` was generated as a temporary configuration
for this run.

All 10 checks passed in **21.11 s**:

| check | result |
|---|---|
| `mfa_version` | PASS |
| `mfa_help` (`g2p`, `validate`, `align`) | PASS |
| Japanese MFA acoustic model | PASS |
| Japanese MFA G2P model | PASS |
| Qwen runtime import | PASS |
| Qwen model cache | PASS |
| Qwen CUDA probe | PASS; CUDA available in the ASR runtime |
| tdmelodic probe | PASS; `sy2a(surface, yomi)` round-tripped the locked reading |
| output path writeability | PASS |
| cache path writeability | PASS |

Successful preflight reason codes are `ok`; the CUDA check may report
`not_required` when the explicit CUDA requirement is disabled. The probes use
bounded subprocesses and project-owned temporary paths.

## Batch results

| run | role / command scope | elapsed | aligned | failed | skipped | reason codes |
|---|---|---:|---:|---:|---:|---|
| `runs/0922jap-full-final2/` | authoritative, all 5 WAV files | 1:41.01 | 2 | 3 | 0 | `unknown_phone` (3) |
| `runs/0922jap-smoke2/` | discovery history, `--limit 3` | 3:12.83 | 1 | 2 | 0 | `malformed_output` (1), `unknown_phone` (1) |
| `runs/0922jap-full/` | discovery history, all 5 WAV files | 6:59.55 | 2 | 3 | 0 | `malformed_output` (1), `unknown_phone` (2) |

The machine-readable summaries are
`runs/0922jap-full-final2/summary.json`,
`runs/0922jap-smoke2/summary.json`, and `runs/0922jap-full/summary.json`;
per-item records are in the corresponding `manifest.jsonl` files. Final2 is
the authoritative batch result.

## Representative aligned outputs

Both aligned items passed final five-tier validation. The tier order is
`original`, `kana`, `phones`, `phone_kana`, `phone_tone`; lower tiers retain
the MFA phone boundaries exactly.

- `runs/0922jap-full-final2/角色__v_liv__v_liv_03/角色__v_liv__v_liv_03.TextGrid`
  contains 5 tiers, 1 non-silence phone (`a`), and tone `L`.
- `runs/0922jap-full-final2/角色__v_liv__v_liv_04/角色__v_liv__v_liv_04.TextGrid`
  contains 5 tiers, 6 non-silence phones, exact lower-tier boundary equality,
  and phone tones `L L H H H H`.

The accompanying traceable evidence is in each item's `alignment.json`,
`frontend.json`, `mora.json`, and `mfa.json` files. The first item also has the
same evidence under `runs/0922jap-full-final2/角色__v_liv__v_liv_03/`.

## Failed items and reason codes

| item | result | evidence and observed cause |
|---|---|---|
| `角色__v_liv__v_liv_01` | failed, `unknown_phone` | After the trailing-marker parser change, the item progressed through accent parsing, G2P, and MFA, then failed phone-map projection. Raw dictionary phones were `ɕ i c i k a ɴ / ɾʲ iː ɸ ɯ / t o / m o ɯ ɕ i / m a s ɨ / c i tː o / j a k ɯ / ɲ i / t a tɕ i / m a s ɨ`. Evidence: `runs/0922jap-full-final2/角色__v_liv__v_liv_01/mfa/dictionary.dict`, `mfa.json`, and `mora.json`. |
| `角色__v_liv__v_liv_02` | failed, `unknown_phone` | MFA emitted `h a i`; projection could not accept `i` because it is absent from the pinned phone map. Evidence: `runs/0922jap-full-final2/角色__v_liv__v_liv_02/mfa/dictionary.dict`, `mfa.json`, and `mora.json`. |
| `角色__v_liv__v_liv_05` | failed, `unknown_phone` | Raw MFA phones were `tɕ i ɡ a i m a s ɨ`; normalized phones were `tɕ i g a i m a s ɨ`. The pinned map is missing `tɕ`, `i`, `g`, `m`, and `ɨ`. Evidence: `runs/0922jap-full-final2/角色__v_liv__v_liv_05/mfa/dictionary.dict`, `mfa.json`, and `mora.json`. |

The authoritative final2 batch reason-code inventory is `unknown_phone` (3).
The preflight also reports `ok`, or `not_required` when the configured CUDA
policy does not require a GPU. The discovery runs retain `malformed_output` as
historical evidence only. Batch isolation kept all failures from stopping the
sibling utterances.

## Real-model tests and verification state

- `pytest -m real_models tests/integration/test_real_qwen.py -v` passed for
  the real Qwen runtime/model check.
- `pytest -m real_models tests/integration/test_real_tdmelodic.py -v` passed
  for the real tdmelodic round-trip check.
- `pytest -m real_models tests/integration/test_real_mfa.py -v` passed for the
  real MFA runtime/model check.
- `pytest -m real_models tests/integration/test_real_pipeline.py -v` passed
  against the existing-output pipeline evidence.
- The default full suite was **204 passed, 4 skipped** at final evidence
  capture.

## Follow-up

1. Decide which observed MFA phones belong in the pinned phone-map expansion
   and add focused coverage before publishing additional aligned outputs.
2. Keep compounds, proper names, numeric readings, abbreviations, mixed
   language, and remaining malformed accent-marker forms as explicit
   follow-up cases in `docs/limitations.md`; use per-occurrence overrides or
   explicit failure codes until they are covered.
