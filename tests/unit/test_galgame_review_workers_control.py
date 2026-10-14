"""The live job can choose review concurrency at the next child boundary."""

import pytest

from tools.galgame_mfa_from_ctc import review_workers_for_run


def test_job_control_is_read_only_from_uuid_work_cache(tmp_path):
    state = tmp_path / "job"
    cache = state / "work" / ("a" * 32) / "cache"
    cache.mkdir(parents=True)
    (state / "review-workers.txt").write_text("8\n")
    assert review_workers_for_run(cache, {}) == 8
    assert review_workers_for_run(cache, {"JAPANMFA_REVIEW_WORKERS": "4"}) == 4


def test_job_control_ignores_unrelated_cache_and_rejects_invalid_count(tmp_path):
    state = tmp_path / "job"
    cache = state / "work" / "not-a-batch" / "cache"
    cache.mkdir(parents=True)
    (state / "review-workers.txt").write_text("8\n")
    assert review_workers_for_run(cache, {}) is None
    valid = state / "work" / ("b" * 32) / "cache"
    valid.mkdir(parents=True)
    (state / "review-workers.txt").write_text("16\n")
    with pytest.raises(ValueError, match="review workers"):
        review_workers_for_run(valid, {})
