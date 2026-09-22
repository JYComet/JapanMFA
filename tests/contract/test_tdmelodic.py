from __future__ import annotations

import sys
from pathlib import Path

import pytest

from japanmfa.accent.tdmelodic import AccentRequest, TdmelodicClient
from japanmfa.errors import StageFailure


@pytest.fixture
def fake_tdmelodic() -> Path:
    return Path(__file__).parents[1] / "fixtures" / "bin" / "fake_tdmelodic.py"


def client(fake_tdmelodic: Path, **env: str) -> TdmelodicClient:
    command = [sys.executable, str(fake_tdmelodic)]
    return TdmelodicClient(command, env=env or None)


def test_client_batches_one_line_per_request_and_preserves_token_mapping(
    fake_tdmelodic: Path, tmp_path: Path
) -> None:
    record = tmp_path / "requests.txt"
    result = TdmelodicClient(
        [sys.executable, str(fake_tdmelodic)],
        env={"FAKE_TDMELODIC_RECORD": str(record)},
    ).predict(
        [
            AccentRequest(3, "学校", "ガッコウ"),
            AccentRequest(7, "猫", "ネコ"),
        ]
    )

    assert result == {3: "ガ[ッコウ]", 7: "ネ[コ"}
    assert record.read_text(encoding="utf-8").splitlines() == [
        "学校,ガッコウ",
        "猫,ネコ",
    ]


@pytest.mark.parametrize(
    ("mode", "reason_code"),
    [
        ("nonzero", "command_failed"),
        ("short", "output_count_mismatch"),
        ("blank", "empty_output"),
    ],
)
def test_client_converts_process_failures_to_stage_failure(
    fake_tdmelodic: Path, mode: str, reason_code: str
) -> None:
    with pytest.raises(StageFailure) as exc_info:
        client(fake_tdmelodic, FAKE_TDMELODIC_MODE=mode).predict(
            [AccentRequest(0, "猫", "ネコ"), AccentRequest(1, "犬", "イヌ")]
        )

    assert exc_info.value.stage == "accent"
    assert exc_info.value.reason_code == reason_code


@pytest.mark.parametrize(
    "request_spec",
    [
        AccentRequest(0, "猫,犬", "ネコ"),
        AccentRequest(0, "猫", "ネコ\nイヌ"),
    ],
)
def test_client_rejects_delimiters_in_input_fields(
    fake_tdmelodic: Path, request_spec: AccentRequest
) -> None:
    with pytest.raises(StageFailure) as exc_info:
        TdmelodicClient([sys.executable, str(fake_tdmelodic)]).predict([request_spec])

    assert exc_info.value.stage == "accent"
    assert exc_info.value.reason_code == "invalid_request"


def test_client_accepts_empty_batch(fake_tdmelodic: Path) -> None:
    assert TdmelodicClient([sys.executable, str(fake_tdmelodic)]).predict([]) == {}
