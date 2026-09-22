# JapanMFA

JapanMFA is a standalone, Japanese-only forced-alignment pipeline. It keeps
the source text and locked kana intact as whole-utterance tiers, obtains final
phone boundaries from Japanese MFA v3, and projects tdmelodic H/L labels onto
those MFA intervals. It is independent of `/home/user/JapMFA` and never uses
or modifies that repository.

## Install isolated runtimes

The orchestrator, MFA, Qwen3-ASR, and tdmelodic are separate runtimes:

```bash
conda env create -f environment.yml
conda env create -f environments/mfa.yml
conda env create -f environments/asr.yml
conda activate japanmfa
pip install -e .
```

The environment manifests pin the versions verified or selected for this
project. The Qwen package pin must be checked against the official Qwen3-ASR
release before creating that environment; this checkout deliberately does not
create environments or download weights.

Install models into project-owned or explicitly configured caches. MFA model
downloads are performed from the MFA environment, for example:

```bash
conda activate japanmfa-mfa
mfa model download acoustic japanese_mfa
mfa model download g2p japanese_mfa
```

The ASR model is local and is selected by `JAPANMFA_ASR_MODEL_PATH`, or by the
standard Hugging Face cache under `HF_HOME`. The default is
`Qwen/Qwen3-ASR-1.7B`; `Qwen/Qwen3-ASR-0.6B` may be configured as a fallback.
No implicit model download happens during `check` or `run`.

## Check and run

Run preflight checks before a real job:

```bash
japanmfa check --config configs/default.yaml
```

The report checks bounded command probes, MFA 3.x, Japanese MFA models, the
Qwen runtime/model, tdmelodic `sy2a`, and temporary child-file writes under the
cache/output directories. Set `JAPANMFA_REQUIRE_CUDA=1` when CPU execution is
explicitly disallowed. Set `JAPANMFA_TDMELODIC_COMMAND` to an isolated
tdmelodic argv-like command and `JAPANMFA_ASR_MODEL_PATH` to a local model
directory when those are not discoverable from the defaults.

```bash
japanmfa run-file /path/to/001.wav --text /path/to/001.txt --output runs/one
japanmfa run --input /mnt/Raw/0922jap --output runs/0922jap-smoke --limit 3
japanmfa run --input /mnt/Raw/0922jap --output runs/0922jap-full
japanmfa inspect runs/0922jap-full/manifest.jsonl
```

An existing same-stem `.txt` is authoritative. Qwen3-ASR still runs in the
validation path and its Japanese result is recorded, but it never silently
rewrites that text. If `.txt` is absent, Japanese-only ASR text is a candidate
and must pass the same frontend checks. Unsupported non-Japanese utterances are
skipped with a reason code; one item failing does not stop the batch.

## Output

Each aligned utterance contains a validated five-tier Praat TextGrid and JSON
audit artifacts. The tiers are exactly:

1. `original` — original source text, one interval covering the complete audio;
2. `kana` — complete locked katakana, one interval covering the complete audio;
3. `phones` — MFA phone intervals, including silence;
4. `phone_kana` — kana projected onto the exact MFA phone intervals;
5. `phone_tone` — H/L projected onto the exact MFA phone intervals.

Only the last three tiers are split at MFA boundaries. A long phone spanning
multiple differently toned morae uses an ordered composite such as `H|L`; no
invented internal boundary is created. See [input/output](docs/input-output.md),
[architecture](docs/architecture.md), and [accent mapping](docs/accent-mapping.md).

## Recovery and diagnostics

The cache is content-fingerprinted and published atomically. Re-running the
same command reuses valid stages; changing text, overrides, model identity, or
audio invalidates downstream stages. Remove only the affected utterance's
project-owned output/cache when recovery requires it. Do not recursively clean
the source corpus, the old JapMFA repository, or a global environment.

Reading overrides, reason codes, unsupported cases, and compound-word follow-up
work are documented in [reading overrides](docs/reading-overrides.md) and
[limitations](docs/limitations.md). Real `0922jap` evidence belongs in the
[Task 12 template](docs/test-report-0922jap.md); the template contains no fake
results.
