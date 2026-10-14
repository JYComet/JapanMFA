"""Controlled per-request native accent results; ordinary predict remains strict."""
from __future__ import annotations
import json
import subprocess
from .tdmelodic import TdmelodicClient, AccentRequest
from japanmfa.errors import StageFailure


class ResidentAccentClient(TdmelodicClient):
    def predict_partial(self, requests):
        outputs, errors, _ = self.predict_partial_detailed(requests)
        return outputs, errors

    def predict_partial_detailed(self, requests):
        requests = tuple(requests)
        if not requests:
            return {}, {}, {}
        indices = [r.token_index for r in requests if isinstance(r, AccentRequest)]
        if len(indices) != len(requests) or len(set(indices)) != len(indices) or any(
                not r.surface or not r.yomi or any(c in r.surface + r.yomi for c in ",\r\n") for r in requests):
            raise StageFailure("accent", "invalid_request", "invalid native accent request")
        command = (*self._command[:-1], "accent-partial")
        try:
            completed = subprocess.run(command, input="".join(f"{r.surface},{r.yomi}\n" for r in requests),
                                       text=True, capture_output=True, check=False, shell=False,
                                       timeout=self._timeout, env=self._env)
        except subprocess.TimeoutExpired as exc:
            raise StageFailure("accent", "command_timeout", "native accent command timed out") from exc
        except OSError as exc:
            raise StageFailure("accent", "command_start_failed", str(exc)) from exc
        if completed.returncode != 0:
            raise StageFailure("accent", "command_failed", completed.stderr[-4000:])
        try:
            value = json.loads(completed.stdout)
            outputs = value["outputs"]
            errors = {int(k): v for k,v in value["errors"].items()}
            repairs = {int(k): v for k,v in value.get("repairs", {}).items()}
            if (len(outputs) != len(requests) or any(not isinstance(s, str) for s in outputs)
                    or any(i not in range(len(requests)) or v not in {"empty_output", "command_failed"} for i,v in errors.items())
                    or any((not out.strip()) != (i in errors) for i,out in enumerate(outputs))
                    or any(i not in range(len(requests)) or i in errors or not isinstance(v, dict)
                           or not isinstance(v.get("raw"), str) or not isinstance(v.get("marked"), str)
                           or v["marked"] != outputs[i].strip() for i,v in repairs.items())):
                raise ValueError("partial coverage differs")
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise StageFailure("accent", "output_coverage_mismatch", "partial native accent coverage differs") from exc
        return ({r.token_index: outputs[i].strip() for i,r in enumerate(requests) if i not in errors},
                {requests[i].token_index: reason for i,reason in errors.items()},
                {requests[i].token_index: repair for i,repair in repairs.items()})
