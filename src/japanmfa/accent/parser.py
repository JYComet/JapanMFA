"""Parse tdmelodic bracket events onto locked morae."""

from __future__ import annotations

import unicodedata
from dataclasses import replace

from japanmfa.domain import Mora
from japanmfa.errors import StageFailure


def _canonical_katakana(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return "".join(
        chr(ord(character) + 0x60)
        if "ぁ" <= character <= "ゖ"
        else character
        for character in normalized
    )


def _failure(reason_code: str, message: str, **details: object) -> StageFailure:
    return StageFailure("accent", reason_code, message, details)


def _boundary_events(
    marked_yomi: str, locked_morae: tuple[Mora, ...]
) -> dict[int, str]:
    """Validate the reading and return one marker event per mora boundary."""
    expected = [_canonical_katakana(mora.kana) for mora in locked_morae]
    if not expected:
        raise _failure("mora_count_mismatch", "cannot parse accent for empty morae")

    canonical = _canonical_katakana(marked_yomi)
    stripped = canonical.replace("[", "").replace("]", "")
    if stripped != "".join(expected):
        raise _failure(
            "reading_mismatch",
            "tdmelodic reading does not equal the locked reading",
            marked_reading=marked_yomi,
            normalized_reading=stripped,
            locked_reading="".join(expected),
        )

    events: dict[int, str] = {}
    mora_index = 0
    character_offset = 0
    while character_offset < len(canonical):
        if canonical[character_offset] in "[]":
            marker = canonical[character_offset]
            if mora_index in events:
                raise _failure(
                    "malformed_output",
                    "multiple accent markers occur at one mora boundary",
                    boundary=mora_index,
                )
            events[mora_index] = marker
            character_offset += 1
            continue

        if mora_index >= len(expected):
            raise _failure("mora_count_mismatch", "marked reading has extra morae")
        mora = expected[mora_index]
        if not canonical.startswith(mora, character_offset):
            raise _failure(
                "malformed_output",
                "accent marker is inside a complete mora boundary",
                boundary=mora_index,
            )
        character_offset += len(mora)
        mora_index += 1

    if mora_index != len(expected):
        raise _failure(
            "mora_count_mismatch",
            "marked reading does not contain every locked mora",
            parsed=mora_index,
            expected=len(expected),
        )
    return events


def parse_accent(
    marked_yomi: str, locked_morae: tuple[Mora, ...]
) -> tuple[Mora, ...]:
    """Assign exactly one Tokyo-style ``H``/``L`` label to each mora.

    Brackets are transitions at mora boundaries.  When the first transition
    is a fall, the first mora starts high; otherwise it starts low.  Events
    must alternate rise and fall.  A trailing fall is allowed to record the
    fall after the final mora, including a redundant terminal fall after
    an already-low final mora. A trailing rise cannot affect a mora.
    """
    if not isinstance(marked_yomi, str):
        raise _failure("malformed_output", "tdmelodic output must be text")
    events = _boundary_events(marked_yomi, locked_morae)
    if len(locked_morae) == 0:  # defensive; _boundary_events already checks it
        raise _failure("mora_count_mismatch", "cannot parse accent for empty morae")

    if 0 in events:
        # A marker before the first mora cannot describe a boundary event.
        raise _failure("malformed_output", "an accent marker cannot precede the first mora")

    first_event = next(iter(events.values()), None)
    pitch = "H" if first_event == "]" else "L"

    tones: list[str] = []
    for index, mora in enumerate(locked_morae):
        if index in events:
            marker = events[index]
            if marker == "[":
                if pitch == "H":
                    raise _failure(
                        "malformed_output",
                        "two rises occur without an intervening fall",
                        boundary=index,
                    )
                pitch = "H"
            elif marker == "]":
                if pitch == "L":
                    raise _failure(
                        "malformed_output",
                        "a fall occurs while pitch is already low",
                        boundary=index,
                    )
                else:
                    pitch = "L"
            else:  # pragma: no cover - events are built from two characters
                raise _failure("malformed_output", "unknown accent marker")

        tones.append(pitch)

    trailing_boundary = len(locked_morae)
    trailing_marker = events.get(trailing_boundary)
    if trailing_marker == "[":
        raise _failure(
            "malformed_output",
            "accent marker must affect a subsequent mora",
            boundary=trailing_boundary,
        )
    if trailing_marker == "]":
        # tdmelodic can emit a closing fall after an already-low final
        # mora (0922jap 0090: ネ]ツ]). It carries no additional tone.
        pitch = "L"

    return tuple(replace(mora, tone=tone) for mora, tone in zip(locked_morae, tones))
