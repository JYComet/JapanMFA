"""Reconcile locked morae with MFA phones and project pitch labels."""

from __future__ import annotations

from dataclasses import dataclass
import unicodedata
from typing import cast

from japanmfa.domain import Mora, PhoneAnnotation, PhoneInterval
from japanmfa.errors import StageFailure
from japanmfa.mfa.lexicon import LockedLexicon
from japanmfa.mfa.phone_map import PhoneMap
from japanmfa.mfa.textgrid import MfaAlignment, MfaPhone


def _failure(reason_code: str, message: str, **details: object) -> StageFailure:
    return StageFailure("projection", reason_code, message, details)


def _canonical_kana(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return "".join(
        chr(ord(character) + 0x60)
        if "ぁ" <= character <= "ゖ"
        else character
        for character in normalized
    )


def labels_for_phone(morae: tuple[Mora, ...]) -> tuple[str, str]:
    kana = "|".join(mora.kana for mora in morae)
    if not kana or any(mora.tone is None for mora in morae):
        raise _failure(
            "unlabeled_phone",
            "every non-silence phone must map to toned morae",
            morae=[mora.kana for mora in morae],
        )
    tone = "|".join(cast(str, mora.tone) for mora in morae)
    return kana, tone


@dataclass(frozen=True)
class _Match:
    cost: int
    count: int
    mapping: tuple[tuple[Mora, ...], ...]


def _better(current: _Match | None, candidate: _Match) -> _Match:
    if current is None or candidate.cost < current.cost:
        return candidate
    if candidate.cost > current.cost:
        return current
    return _Match(current.cost, min(2, current.count + candidate.count), current.mapping)


def _match_morae_to_phones(
    morae: tuple[Mora, ...], phones: tuple[str, ...], phone_map: PhoneMap
) -> tuple[tuple[Mora, ...], ...]:
    normalized = tuple(phone_map.normalize(phone) for phone in phones)
    states: dict[tuple[int, int], _Match] = {(0, 0): _Match(0, 1, ())}
    for mora_index in range(len(morae) + 1):
        for phone_index in range(len(normalized) + 1):
            state = states.get((mora_index, phone_index))
            if state is None:
                continue
            for rule in phone_map.rules:
                mora_end = mora_index + len(rule.kana)
                phone_end = phone_index + len(rule.phones)
                if mora_end > len(morae) or phone_end > len(normalized):
                    continue
                if tuple(mora.kana for mora in morae[mora_index:mora_end]) != rule.kana:
                    continue
                if normalized[phone_index:phone_end] != rule.phones:
                    continue
                group = tuple(morae[mora_index:mora_end])
                mapping = state.mapping + (group,) * len(rule.phones)
                candidate = _Match(state.cost + rule.cost, state.count, mapping)
                states[(mora_end, phone_end)] = _better(states.get((mora_end, phone_end)), candidate)

    result = states.get((len(morae), len(normalized)))
    if result is None:
        if any(phone not in phone_map.known_phones for phone in normalized):
            raise _failure(
                "unknown_phone",
                "aligned MFA phone is not in the pinned phone map",
                phones=list(phones),
            )
        raise _failure(
            "mora_phone_mapping",
            "MFA phones cannot be grouped into the locked mora sequence",
            morae=[mora.kana for mora in morae],
            phones=list(phones),
        )
    if result.count != 1:
        raise _failure(
            "ambiguous_mora_phone_mapping",
            "more than one lowest-cost mora-to-phone grouping exists",
            morae=[mora.kana for mora in morae],
            phones=list(phones),
            cost=result.cost,
        )
    return result.mapping


def _validate_token_morae(lexicon: LockedLexicon, token_morae: dict[int, tuple[Mora, ...]]) -> None:
    expected = {token.index for token in lexicon.tokens}
    if set(token_morae) != expected:
        raise _failure(
            "mora_coverage_mismatch",
            "token_morae must contain exactly one entry for each locked token",
            expected=sorted(expected),
            actual=sorted(token_morae),
        )
    for token in lexicon.tokens:
        morae = token_morae[token.index]
        if not morae or any(mora.token_index != token.index for mora in morae):
            raise _failure(
                "mora_coverage_mismatch",
                "token morae must be non-empty and belong to their token",
                token_index=token.index,
            )
        if any(mora.index_in_token != index for index, mora in enumerate(morae)):
            raise _failure(
                "mora_reading_mismatch",
                "token mora indices must be contiguous and ordered",
                token_index=token.index,
                indices=[mora.index_in_token for mora in morae],
            )
        reconstructed = "".join(_canonical_kana(mora.kana) for mora in morae)
        locked = _canonical_kana(token.reading)
        if reconstructed != locked:
            raise _failure(
                "mora_reading_mismatch",
                "token morae must reconstruct the locked token reading",
                token_index=token.index,
                reconstructed=reconstructed,
                locked=locked,
            )


def _word_phone_indices(alignment: MfaAlignment, alias: str) -> list[int]:
    return [
        index
        for index, phone in enumerate(alignment.phones)
        if not phone.is_silence and phone.word_alias == alias
    ]


def _reconcile_words(
    alignment: MfaAlignment,
    lexicon: LockedLexicon,
    token_morae: dict[int, tuple[Mora, ...]],
    phone_map: PhoneMap,
) -> dict[int, tuple[Mora, ...]]:
    aliases = tuple(word.alias for word in alignment.words)
    if aliases != lexicon.aliases:
        raise _failure(
            "word_alias_mismatch",
            "MFA word aliases must equal locked lexicon aliases in order",
            expected=list(lexicon.aliases),
            actual=list(aliases),
        )

    phone_to_morae: dict[int, tuple[Mora, ...]] = {}
    for word, pronunciation, token in zip(
        alignment.words, lexicon.pronunciations, lexicon.tokens
    ):
        indices = _word_phone_indices(alignment, word.alias)
        aligned = tuple(phone_map.normalize(alignment.phones[index].label) for index in indices)
        expected = tuple(phone_map.normalize(phone) for phone in pronunciation.phones)
        if aligned != expected:
            raise _failure(
                "phone_sequence_mismatch",
                "ordered non-silence MFA phones differ from the locked pronunciation",
                alias=word.alias,
                expected=list(expected),
                actual=[alignment.phones[index].label for index in indices],
            )
        mapping = _match_morae_to_phones(token_morae[token.index], aligned, phone_map)
        for index, morae in zip(indices, mapping):
            phone_to_morae[index] = morae
    return phone_to_morae


def _annotation(phone: MfaPhone, morae: tuple[Mora, ...] | None) -> PhoneAnnotation:
    interval = PhoneInterval(phone.start, phone.end, phone.label)
    if phone.is_silence:
        return PhoneAnnotation(interval, None, (), "", "", True)
    if morae is None:
        raise _failure(
            "unmapped_phone",
            "every non-silence MFA phone must be reconciled",
            label=phone.label,
        )
    kana_label, tone_label = labels_for_phone(morae)
    token_index = morae[0].token_index
    if any(mora.token_index != token_index for mora in morae):
        raise _failure(
            "cross_token_mapping",
            "a phone cannot map across token boundaries",
            label=phone.label,
        )
    return PhoneAnnotation(interval, token_index, morae, kana_label, tone_label, False)


def project_annotations(
    alignment: MfaAlignment,
    lexicon: LockedLexicon,
    token_morae: dict[int, tuple[Mora, ...]],
    phone_map: PhoneMap,
) -> tuple[PhoneAnnotation, ...]:
    """Project toned locked morae onto unchanged MFA phone intervals."""
    _validate_token_morae(lexicon, token_morae)
    phone_to_morae = _reconcile_words(alignment, lexicon, token_morae, phone_map)
    return tuple(
        _annotation(phone, None if phone.is_silence else phone_to_morae.get(index))
        for index, phone in enumerate(alignment.phones)
    )


__all__ = ["labels_for_phone", "project_annotations"]
