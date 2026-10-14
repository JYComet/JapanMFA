import json

from tools.galgame_mfa_dual_service import summarize_report


def test_monitor_records_complete_batch_metrics_without_source_results(tmp_path):
    path = tmp_path / 'batch.json'
    path.write_text(json.dumps({'report': {
        'resident_count': 2, 'source_count': 2000, 'prepared_count': 1900,
        'published_or_retained': 900, 'total_seconds': 280,
        'phase_seconds': {'mfa_align': 70, 'mfa_align_service_sum': 130,
                          'timed_review': 45, 'publication': 100},
        'mfa_batches': {'timed': {'files': 6500}, 'context_retry': {'files': 1400}},
        'results': [{'stem': 'sensitive-source'}],
    }}))
    summary = summarize_report(path)
    assert summary['resident_count'] == 2
    assert summary['mfa_align_seconds'] == 70
    assert summary['mfa_service_seconds'] == 130
    assert summary['published'] == 900
    assert 'results' not in summary
