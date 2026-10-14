#!/usr/bin/env bash
# Start only after the JapGalgame CTC timestamp job has finished.
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
export PATH="$repo_dir/.runtime/envs/mfa/bin:$PATH"
export MFA_ROOT_DIR="$repo_dir/.runtime/mfa-root"
export JAPANMFA_TDMELODIC_COMMAND='docker run --rm -i japanmfa-tdmelodic:e7fdb63f85bb'
export PYTHONPATH="$repo_dir/src:$repo_dir${PYTHONPATH:+:$PYTHONPATH}"

exec "$repo_dir/.runtime/envs/orchestrator/bin/python" -u \
  "$repo_dir/tools/galgame_mfa_all.py" \
  --source /mnt/Raw/JapGalgame \
  --output /mnt/Raw/GalgameMFA \
  --state "$repo_dir/.runtime/jobs/galgame-mfa-all" \
  --config "$repo_dir/runs/0922jap-internal-ellipsis-20260929T084752Z/final-config.yaml" \
  "$@"
