"""Expected, typed errors used to isolate pipeline outcomes."""

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class SkipUtterance(Exception):
    """An input is known to be outside the supported Japanese scope."""

    reason_code: str
    message: str
    details: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)

@dataclass(frozen=True)
class StageFailure(Exception):
    """A supported input failed while a named pipeline stage was running."""

    stage: str
    reason_code: str
    message: str
    details: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)
