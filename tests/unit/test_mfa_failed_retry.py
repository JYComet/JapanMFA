from __future__ import annotations
import sys
from pathlib import Path
import pytest
from japanmfa.mfa.failed_retry import wrap_compiled_alignment, failed_retry_command

class Graph:
    def __init__(self, weight=0):
        self.weight = weight
    def Copy(self):
        return Graph(self.weight)

def result(success, label="old"):
    return ([label], [7], -8.5, [1.25], success, True)

def test_success_keeps_exact_native_result_without_wider_search():
    accepted = result(True)
    calls = []
    def native(*args, **options):
        calls.append(options["retry_beam"])
        return accepted
    actual = wrap_compiled_alignment(native)(None, None, Graph(), object(), beam=10, retry_beam=40)
    assert actual is accepted
    assert calls == [40]

def test_failed_original_retries_pristine_graph_and_preserves_all_native_fields():
    recovered = result(True, "recovered")
    waves = object()
    calls = []
    def native(_transition, _model, graph, features, **options):
        assert features is waves
        calls.append((options["retry_beam"], graph.weight))
        graph.weight += 100
        return result(False) if options["retry_beam"] == 40 else recovered
    actual = wrap_compiled_alignment(native)(None, None, Graph(), waves, beam=10, retry_beam=40,
        acoustic_scale=.083333, transition_scale=1., self_loop_scale=.1, careful=False)
    assert actual is recovered
    assert calls == [(40, 0), (160, 0)]
    assert actual[3] == [1.25]

def test_failed_additional_search_stays_failed():
    calls = []
    def native(*args, **options):
        calls.append(options["retry_beam"])
        return result(False)
    actual = wrap_compiled_alignment(native)(None, None, Graph(), object(), beam=10, retry_beam=40)
    assert actual[4] is False
    assert calls == [40, 160]

@pytest.mark.parametrize("beam,retry", [(5,40),(10,80),(20,40)])
def test_other_search_settings_are_not_changed(beam, retry):
    calls = []
    failed = result(False)
    def native(*args, **options):
        calls.append((options["beam"], options["retry_beam"]))
        return failed
    assert wrap_compiled_alignment(native)(None,None,Graph(),object(),beam=beam,retry_beam=retry) is failed
    assert calls == [(beam,retry)]

def test_native_exception_is_not_retried():
    calls = []
    def native(*args, **options):
        calls.append(1)
        raise RuntimeError("native decoder exception")
    with pytest.raises(RuntimeError, match="native decoder exception"):
        wrap_compiled_alignment(native)(None,None,Graph(),object(),beam=10,retry_beam=40)
    assert calls == [1]

def test_command_uses_the_pinned_mfa_interpreter(tmp_path):
    executable = tmp_path / "mfa"
    executable.write_text("#!" + sys.executable + "\n")
    command = failed_retry_command((str(executable),))
    assert command[0] == sys.executable
    assert Path(command[1]).name == "failed_retry.py"
    assert command[2] == str(executable.resolve())
    assert len(command) == 3

def test_non_python_command_cannot_silently_bypass_retry(tmp_path):
    executable = tmp_path / "mfa"
    executable.write_text("#!/bin/sh\n")
    with pytest.raises(ValueError, match="Python"):
        failed_retry_command((str(executable),))
