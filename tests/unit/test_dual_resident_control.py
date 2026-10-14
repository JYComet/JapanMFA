import socket
from pathlib import Path

import pytest

from tools.galgame_mfa_from_ctc import resident_sockets_for_run


def test_production_job_control_enables_two_live_residents(tmp_path):
    state = tmp_path / "state"
    cache = state / "work" / ("a" * 32) / "cache"
    cache.mkdir(parents=True)
    first = state / "native-resident.sock"
    second = state / "native-resident-2.sock"
    listeners = [socket.socket(socket.AF_UNIX) for _ in range(2)]
    for listener, path in zip(listeners, (first, second)):
        listener.bind(str(path))
    try:
        assert resident_sockets_for_run(cache, {"JAPANMFA_NATIVE_SOCKET": str(first)}) is None
        (state / "dual-resident.enabled").write_text("2\n")
        assert resident_sockets_for_run(cache, {"JAPANMFA_NATIVE_SOCKET": str(first)}) == (first, second)
        assert resident_sockets_for_run(cache, {"JAPANMFA_NATIVE_SOCKET": str(second)}) is None
        assert resident_sockets_for_run(tmp_path / "other" / "cache",
                                        {"JAPANMFA_NATIVE_SOCKET": str(first)}) is None
    finally:
        for listener in listeners:
            listener.close()


def test_enabled_job_fails_before_alignment_if_second_socket_is_missing(tmp_path):
    state = tmp_path / "state"
    cache = state / "work" / ("b" * 32) / "cache"
    cache.mkdir(parents=True)
    (state / "dual-resident.enabled").write_text("2\n")
    with pytest.raises(ValueError, match="second MFA resident socket"):
        resident_sockets_for_run(cache, {"JAPANMFA_NATIVE_SOCKET": str(state / "native-resident.sock")})
