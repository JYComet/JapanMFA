#!/usr/bin/env bash
# Resume the completed JapGalgame catalog with two independent workers per GPU.
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
job_root="$repo_dir/.runtime/jobs"
catalog_dir="$job_root/japgalgame-ctc-20260928"
full_dir="$job_root/japgalgame-ctc-full16-20260928"
catalog_pid=1611006

while [[ ! -f "$catalog_dir/catalog_summary.json" ]]; do
  if ! kill -0 "$catalog_pid" 2>/dev/null; then
    echo "catalog exited without a completed summary" >&2
    exit 1
  fi
  sleep 30
done

"$repo_dir/.runtime/envs/orchestrator/bin/python" - <<'PY'
from pathlib import Path

root = Path('/mnt/Raw/JapGalgame')
created = 0
for category in root.iterdir():
    if category.is_dir() and ((category / 'wav').is_dir() or (category / 'txt').is_dir()):
        target = category / 'ctc'
        if target.is_symlink():
            raise SystemExit(f'ctc directory is a symlink: {target}')
        if not target.exists():
            target.mkdir(exist_ok=True)
            created += 1
print(f'ctc directories ready; created={created}', flush=True)
PY

for wave in wave1 wave2; do
  wave_dir="$job_root/japgalgame-ctc-${wave}-20260928"
  status_file="$wave_dir/supervisor.json"
  if [[ ! -f "$status_file" ]]; then
    continue
  fi
  read -r pid status < <("$repo_dir/.runtime/envs/orchestrator/bin/python" - "$status_file" <<'PY'
import json
import sys
value = json.load(open(sys.argv[1], encoding='utf-8'))
print(value['pid'], value['status'])
PY
)
  if [[ "$status" == running ]] && kill -0 "$pid" 2>/dev/null; then
    echo "stopping ${wave} supervisor PID $pid before complete-manifest resume"
    kill -TERM "$pid"
    for attempt in {1..120}; do
      if ! kill -0 "$pid" 2>/dev/null; then break; fi
      sleep 5
    done
    if kill -0 "$pid" 2>/dev/null; then
      echo "${wave} supervisor did not stop within ten minutes" >&2
      exit 1
    fi
  fi
done

if [[ ! -f "$full_dir/catalog_summary.json" ]]; then
  "$repo_dir/.runtime/envs/orchestrator/bin/python" -u \
    "$repo_dir/tools/galgame_qwen_ctc.py" reshard \
    --source-state "$catalog_dir" --state "$full_dir" --shards 16
fi

exec "$repo_dir/.runtime/envs/orchestrator/bin/python" -u \
  "$repo_dir/tools/galgame_qwen_ctc_supervisor.py" \
  --state "$full_dir" \
  --python "$repo_dir/.runtime/envs/asr/bin/python3.10" \
  --gpus 8 --workers 16 --batch-size 16 \
  --model "$repo_dir/.runtime/models/qwen3-forced-aligner-0.6b"
