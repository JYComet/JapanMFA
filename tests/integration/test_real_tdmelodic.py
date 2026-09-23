from __future__ import annotations

import os
import shlex

import pytest

from japanmfa.accent.parser import parse_accent
from japanmfa.accent.tdmelodic import AccentRequest, TdmelodicClient
from japanmfa.domain import Token
from japanmfa.frontend.mora import segment_morae


pytestmark = pytest.mark.real_models


def _command() -> tuple[str, ...]:
    raw = os.environ.get("JAPANMFA_REAL_TDMELODIC_COMMAND")
    if not raw:
        pytest.skip("set JAPANMFA_REAL_TDMELODIC_COMMAND to opt into the real tdmelodic test")
    command = tuple(shlex.split(raw))
    if not command:
        pytest.skip("JAPANMFA_REAL_TDMELODIC_COMMAND is empty")
    return command


def test_real_tdmelodic_round_trips_locked_yomi_through_parser() -> None:
    token = Token(0, 0, 2, "学校", ("名詞",), "ガッコウ", "override")
    morae = segment_morae(token)
    marked = TdmelodicClient(_command()).predict(
        [AccentRequest(token.index, token.surface, token.reading)]
    )[token.index]

    assert marked.replace("[", "").replace("]", "") == token.reading
    toned = parse_accent(marked, morae)
    assert tuple(mora.kana for mora in toned) == tuple(mora.kana for mora in morae)
    assert all(mora.tone in {"H", "L"} for mora in toned)
