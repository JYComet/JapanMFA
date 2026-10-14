import threading
from tools.preparation_windows import PreparationWindows


def test_next_preparation_overlaps_alignment_and_only_owner_commits():
    aligning = threading.Event()
    prepared_second = threading.Event()
    owner = threading.get_ident()
    commits = []
    def prepare(work):
        if work == 2:
            assert aligning.wait(2)
            prepared_second.set()
        return 0
    def align(work):
        if work == 1:
            aligning.set()
            assert prepared_second.wait(2)
        return 1
    def commit(work, code):
        assert threading.get_ident() == owner
        assert code == 1
        commits.append(work)
    with PreparationWindows(prepare, align, commit) as windows:
        windows.submit(1)
        windows.submit(2)
    assert commits == [1,2]


def test_failed_preparation_never_aligns_or_commits():
    import pytest
    calls = []
    with pytest.raises(RuntimeError, match="preparation"):
        with PreparationWindows(lambda x:2, lambda x:calls.append(x), lambda *x:calls.append(x)) as windows:
            windows.submit(1)
    assert calls == []
