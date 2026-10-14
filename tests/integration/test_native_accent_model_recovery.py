"""Pinned native model must only repair lexically corroborated accents."""

import json
import os
import subprocess

import pytest


@pytest.mark.real_models
def test_native_accent_recovery_preserves_raw_disagreement():
    image = os.environ.get("JAPANMFA_REAL_TDMELODIC_IMAGE")
    if not image:
        pytest.skip("set JAPANMFA_REAL_TDMELODIC_IMAGE to run native accent recovery")
    from japanmfa.mfa.native_resident import ACCENT_CODE, ACCENT_RECOVERY_SOURCE

    request = {"lines": ["あなた,アナタ", "こんにちは,コンニチハ", "学校,ガッコウ"], "partial": True}
    result = subprocess.run(
        ["docker", "run", "--rm", "-i", "--mount",
         f"type=bind,src={ACCENT_RECOVERY_SOURCE},dst=/tmp/japanmfa_accent_model_recovery.py,readonly",
         "--entrypoint", "python", image, "-u", "-c", ACCENT_CODE],
        input=json.dumps(request, ensure_ascii=False) + "\n", text=True,
        capture_output=True, check=False, timeout=120,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["code"] == 0, payload
    assert payload["outputs"] == ["ア[ナ]タ", "コ]ンニチ]ハ]", "ガ[ッコウ"]
    assert payload["repairs"]["0"]["raw"] == "ア]ナ]タ"
    assert "1" not in payload["repairs"]
    assert "2" not in payload["repairs"]
