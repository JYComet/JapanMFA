from types import SimpleNamespace
from japanmfa.domain import UtteranceOutcome
from tools import galgame_mfa_hybrid as hybrid
import threading
import time
import pytest
import socket as unix_socket

def test_timed_batch_reviews_every_prepared_source_without_whole_candidate(tmp_path, monkeypatch):
    run = tmp_path / "run"; run.mkdir()
    input_root = tmp_path / "input"; input_root.mkdir()
    (input_root / "sample.wav").write_bytes(b"audio")
    (input_root / "sample.txt").write_text("source")
    item = SimpleNamespace(utterance_id="sample")
    failed = UtteranceOutcome("sample", "failed", "alignment_acoustic_coverage", None, run, {})
    calls = []
    class Pipeline:
        def prepare_mfa_inputs(self, *args):
            return SimpleNamespace(items=(item,), failures=())
        def review_mfa_inputs(self, *args):
            return SimpleNamespace(outcomes=(failed,))
    def pipeline(*args, **kwargs):
        calls.append(kwargs.get("mode", "timed")); return Pipeline()
    monkeypatch.setattr(hybrid, "_pipeline", pipeline)
    batch = SimpleNamespace(entries={"crop": item})
    def build(items, root, kind):
        assert kind == "timed"; return batch
    monkeypatch.setattr(hybrid, "build_batch_corpus", build, raising=False)
    monkeypatch.setattr(hybrid, "_batch_align", lambda *args: ({}, 0.0))
    monkeypatch.setattr(hybrid, "BatchGridRunner", lambda *args, **kwargs: object())
    report = hybrid.run_timed_batch(input_root, [{"stem":"sample"}], run, tmp_path/"out", object(), object(), lambda *args: {}, lambda *args: "sha")
    assert report["strategy"] == "ctc_timed_batch_resident"
    assert report["results"][0]["published"] is False
    assert report["results"][0]["whole_reason"] == "alignment_acoustic_coverage"
    assert calls == ["timed", "timed"]


def test_acoustic_groups_cover_failed_and_prepared_sources_exactly_once(tmp_path):
    preparation = SimpleNamespace(items=(), failures=(UtteranceOutcome("bad", "failed", "mapping", None, None, {}),))
    for groups in ([["foreign"]], [["bad", "bad"]], [[]]):
        with pytest.raises(ValueError, match="cover every source"):
            hybrid.run_timed_batch(tmp_path, [{"stem":"bad"}], tmp_path, tmp_path/"out", object(), object(),
                                   lambda *args: {}, lambda *args: "sha", preparation=preparation, acoustic_groups=groups)


def test_two_residents_align_original_groups_concurrently_in_order(tmp_path, monkeypatch):
    sockets = (tmp_path / "one.sock", tmp_path / "two.sock")
    listeners = [unix_socket.socket(unix_socket.AF_UNIX) for _ in sockets]
    for listener, socket in zip(listeners, sockets):
        listener.bind(str(socket))
    barrier = threading.Barrier(2, timeout=2)
    seen = []
    lock = threading.Lock()

    def align(config, batch, *, socket=None):
        with lock:
            seen.append((batch, socket))
        barrier.wait()
        time.sleep(0.01 if batch == 0 else 0.03)
        return {str(batch): socket}, 0.02

    monkeypatch.setattr(hybrid, "_batch_align", align)
    outputs, wall = hybrid._align_batches(None, [0, 1], sockets)
    assert [item[0] for item in outputs] == [{"0": sockets[0]}, {"1": sockets[1]}]
    assert set(seen) == {(0, sockets[0]), (1, sockets[1])}
    assert wall >= 0.03
    for listener in listeners:
        listener.close()


def test_resident_sockets_must_be_distinct_and_present(tmp_path):
    first = tmp_path / "one.sock"
    listener = unix_socket.socket(unix_socket.AF_UNIX)
    listener.bind(str(first))
    for sockets in ((first, first), (first, tmp_path / "missing.sock")):
        with pytest.raises(ValueError, match="resident sockets"):
            hybrid._align_batches(None, [object()], sockets)
    listener.close()


def test_each_resident_runs_one_group_at_a_time_and_failure_propagates(tmp_path, monkeypatch):
    sockets = (tmp_path / "one.sock", tmp_path / "two.sock")
    listeners = [unix_socket.socket(unix_socket.AF_UNIX) for _ in sockets]
    for listener, path in zip(listeners, sockets):
        listener.bind(str(path))
    active = {path.resolve(): 0 for path in sockets}
    lock = threading.Lock()

    def align(config, batch, *, socket=None):
        with lock:
            active[socket] += 1
            assert active[socket] == 1
        time.sleep(0.01)
        with lock:
            active[socket] -= 1
        if batch == 3:
            raise RuntimeError("resident failed")
        return {str(batch): socket}, 0.01

    monkeypatch.setattr(hybrid, "_batch_align", align)
    with pytest.raises(RuntimeError, match="resident failed"):
        hybrid._align_batches(None, [0, 1, 2, 3], sockets)
    assert all(value == 0 for value in active.values())
    for listener in listeners:
        listener.close()
