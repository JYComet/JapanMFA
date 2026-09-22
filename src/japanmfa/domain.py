"""Immutable records shared by JapanMFA pipeline stages."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping, TypeAlias

OutcomeStatus: TypeAlias = Literal["aligned", "skipped", "failed"]


@dataclass(frozen=True)
class Utterance:
    utterance_id: str
    audio_path: Path
    text_path: Path | None


@dataclass(frozen=True)
class SourceText:
    original: str
    processing: str
    source: Literal["txt", "asr"]


@dataclass(frozen=True)
class Token:
    index: int
    start: int
    end: int
    surface: str
    part_of_speech: tuple[str, ...]
    reading: str
    reading_source: Literal["sudachi", "override"]


@dataclass(frozen=True)
class Mora:
    token_index: int
    index_in_token: int
    kana: str
    tone: Literal["H", "L"] | None = None


@dataclass(frozen=True)
class Pronunciation:
    reading: str
    phones: tuple[str, ...]


@dataclass(frozen=True)
class PhoneInterval:
    start: float
    end: float
    label: str

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError("end must be greater than start")


@dataclass(frozen=True)
class PhoneAnnotation:
    interval: PhoneInterval
    token_index: int | None
    morae: tuple[Mora, ...]
    kana_label: str
    tone_label: str
    is_silence: bool


@dataclass(frozen=True)
class UtteranceOutcome:
    utterance_id: str
    status: OutcomeStatus
    reason_code: str | None
    message: str | None
    artifact_dir: Path | None
    stage_durations: Mapping[str, float]
