from dataclasses import replace
import hashlib
from test_pipeline_fake_backends import _pipeline, _write_audio, EchoAccent, FakeAudio
import os
import time

class WorkerAudio(FakeAudio):
    def prepare(self, source, destination):
        value = super().prepare(source, destination)
        (destination.parent / "worker.pid").write_text(str(os.getpid()))
        time.sleep(0.1)
        return value


def test_process_preparation_keeps_order_and_locked_inputs(tmp_path):
    inp = tmp_path / "input"
    for name in ("h", "f", "c", "a", "g", "e", "b", "d"):
        _write_audio(inp, name)
    snapshots = []
    for workers in (1, 4):
        pipeline = _pipeline(accent=EchoAccent())
        pipeline.config = replace(pipeline.config, paths=replace(pipeline.config.paths, cache_dir=tmp_path/f"cache-{workers}"))
        pipeline.audio_normalizer = WorkerAudio()
        pipeline.batch_preparation = True
        pipeline.preparation_workers = workers
        out = tmp_path/f"out-{workers}"
        result = pipeline.prepare_mfa_inputs(inp, out, None)
        assert [x.utterance_id for x in result.items] == list("abcdefgh")
        assert not result.failures
        if workers > 1:
            pids = {int(p.read_text()) for p in (tmp_path/f"cache-{workers}/audio").glob("*/worker.pid")}
            assert os.getpid() not in pids
            assert len(pids) > 1
        snapshots.append({(x.utterance_id, name): (x.artifact_dir/name).read_bytes()
                          for x in result.items for name in ("frontend.json", "mora.json", "mfa/dictionary.dict", "mfa/corpus/aliases.json")})
        batch = pipeline.review_mfa_inputs(result, tmp_path/f"review-{workers}")
        assert all(x.status == "aligned" for x in batch.outcomes)
    assert snapshots[0] == snapshots[1]
