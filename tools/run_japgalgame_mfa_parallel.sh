#!/usr/bin/env bash
# Parallel CPU MFA launcher. Refuses to overlap the existing serial supervisor.
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
export PYTHONPATH="$repo_dir/src:$repo_dir${PYTHONPATH:+:$PYTHONPATH}"

exec "$repo_dir/.runtime/envs/orchestrator/bin/python" -u \
  "$repo_dir/tools/galgame_mfa_parallel.py" "$@"
