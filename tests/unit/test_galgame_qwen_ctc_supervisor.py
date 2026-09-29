from __future__ import annotations

import json
from pathlib import Path

from tools.galgame_qwen_ctc_supervisor import assigned_gpu, completion_status, summarize_states


def test_shards_are_spread_evenly_across_eight_gpus() -> None:
    assert [assigned_gpu(index, 8) for index in range(16)] == list(range(8)) * 2


def test_summarize_states_keeps_processed_and_failed_counts_distinct(tmp_path: Path) -> None:
    (tmp_path / 'catalog_summary.json').write_text(json.dumps({
        'paired': 5, 'missing_txt': 1, 'missing_wav': 2, 'shard_counts': [2, 3]
    }))
    (tmp_path / 'worker_0.json').write_text(json.dumps({
        'status': 'complete', 'seen': 2, 'total': 2, 'done': 1, 'existing': 1, 'failed': 0
    }))
    (tmp_path / 'worker_1.json').write_text(json.dumps({
        'status': 'running', 'seen': 2, 'total': 3, 'done': 1, 'existing': 0, 'failed': 1
    }))

    summary = summarize_states(tmp_path, 2)

    assert summary['paired'] == 5
    assert summary['success'] == 3
    assert summary['failed'] == 1
    assert summary['remaining'] == 1
    assert summary['missing_txt'] == 1
    assert summary['workers_complete'] == 1


def test_completion_status_reports_unprocessed_or_failed_pairs() -> None:
    clean = {'paired': 2, 'success': 2, 'failed': 0, 'missing_txt': 0,
             'missing_wav': 0, 'remaining': 0}
    assert completion_status(clean, workers_complete=2, workers=2) == 'complete'
    assert completion_status({**clean, 'failed': 1, 'success': 1}, workers_complete=2, workers=2) == 'complete_with_failures'
    assert completion_status({**clean, 'remaining': 1}, workers_complete=1, workers=2) == 'attention_required'
