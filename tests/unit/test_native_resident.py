from pathlib import Path
from multiprocessing import Pipe
import pytest
from japanmfa.mfa.native_resident import ContentModelCache, validate_request

def test_model_cache_is_content_based_and_changed_bytes_reload(tmp_path):
    first = tmp_path / "one.mdl"; second = tmp_path / "two.mdl"
    first.write_bytes(b"model-one"); second.write_bytes(first.read_bytes())
    calls = []
    def read(path):
        calls.append(path); return object()
    cache = ContentModelCache(read)
    a = cache(first)
    assert cache(second) is a
    second.write_bytes(b"model-two")
    assert cache(second) is not a
    assert len(calls) == 2
    assert cache.hits == 1 and cache.loads == 2

def test_failed_model_read_is_not_cached(tmp_path):
    model = tmp_path / "model.mdl"; model.write_bytes(b"bad")
    def read(path):
        raise ValueError("invalid native model")
    cache = ContentModelCache(read)
    for _ in range(2):
        with pytest.raises(ValueError): cache(model)
    assert cache.loads == 0

def test_native_resident_refuses_cross_job_and_multiple_job_alignment(tmp_path):
    own = tmp_path / "own"; own.mkdir()
    foreign = tmp_path / "foreign"; foreign.mkdir()
    args = ["align", str(own / "corpus"), str(own / "dict"), "japanese_mfa", str(own / "out"), "--temporary_directory", str(own / "work"), "--num_jobs", "1"]
    validate_request(args, own)
    for changed in ([*args[:-1], "2"], [args[0], str(foreign), *args[2:]]):
        with pytest.raises(ValueError): validate_request(changed, own)


def test_resident_keeps_serving_after_client_disconnects_before_request():
    from japanmfa.mfa import native_resident

    server, client = Pipe()
    client.close()
    try:
        assert native_resident.receive_request(server) is None
    finally:
        server.close()

    server, client = Pipe()
    try:
        client.send({"args": ["align"]})
        assert native_resident.receive_request(server) == {"args": ["align"]}
    finally:
        client.close()
        server.close()


def test_resident_keeps_serving_after_client_disconnects_before_response():
    from japanmfa.mfa import native_resident

    server, client = Pipe()
    client.close()
    try:
        assert native_resident.send_response(server, {"code": 0}) is False
    finally:
        server.close()

    server, client = Pipe()
    try:
        assert native_resident.send_response(server, {"code": 0}) is True
        assert client.recv() == {"code": 0}
    finally:
        client.close()
        server.close()
