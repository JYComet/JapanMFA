import json
import subprocess
import pytest
from japanmfa.accent.resident import ResidentAccentClient
from japanmfa.accent.tdmelodic import AccentRequest, TdmelodicClient
from japanmfa.errors import StageFailure


def test_partial_preserves_good_native_output_and_failure_identity(monkeypatch):
    def run(args, **kw):
        assert args[-1] == "accent-partial"
        return subprocess.CompletedProcess(args, 0, json.dumps({"outputs": ["キョ[ウ", ""], "errors": {"1": "empty_output"}}), "")
    monkeypatch.setattr(subprocess, "run", run)
    requests = [AccentRequest(4,"今日","キョウ"), AccentRequest(9,"京","キョオ")]
    assert ResidentAccentClient(("python","native","call","socket","accent")).predict_partial(requests) == ({4:"キョ[ウ"},{9:"empty_output"})


def test_partial_detailed_keeps_native_repair_evidence(monkeypatch):
    repair = {"raw": "ア]ナ]タ", "marked": "ア[ナ]タ", "accent": 2, "evidence": "unidic"}
    def run(args, **kw):
        return subprocess.CompletedProcess(args, 0, json.dumps({
            "outputs": ["ア[ナ]タ", ""], "errors": {"1": "empty_output"},
            "repairs": {"0": repair}}), "")
    monkeypatch.setattr(subprocess, "run", run)
    requests = [AccentRequest(4, "あなた", "アナタ"), AccentRequest(9, "京", "キョオ")]
    assert ResidentAccentClient(("python", "native", "call", "socket", "accent")).predict_partial_detailed(requests) == (
        {4: "ア[ナ]タ"}, {9: "empty_output"}, {4: repair})


def test_partial_detailed_rejects_inconsistent_repair_evidence(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda args, **kw: subprocess.CompletedProcess(args, 0, json.dumps({
        "outputs": ["ア[ナ]タ"], "errors": {},
        "repairs": {"0": {"raw": "ア]ナ]タ", "marked": "ア]ナ]タ"}}}), ""))
    with pytest.raises(StageFailure, match="coverage"):
        ResidentAccentClient(("python", "native", "call", "socket", "accent")).predict_partial_detailed(
            [AccentRequest(4, "あなた", "アナタ")])


def test_generic_adapter_still_rejects_empty_and_partial_protocol_rejects_missing(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a,0,"キョ[ウ\n\n",""))
    requests = [AccentRequest(0,"今日","キョウ"), AccentRequest(1,"京","キョオ")]
    with pytest.raises(StageFailure, match="empty"):
        TdmelodicClient(("native",)).predict(requests)
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a,0,json.dumps({"outputs":["キョ[ウ"],"errors":{}}),""))
    with pytest.raises(StageFailure, match="coverage"):
        ResidentAccentClient(("python","native","call","socket","accent")).predict_partial(requests)
