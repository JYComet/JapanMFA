"""Lossless mora-group aliases for a single bounded MFA recovery attempt."""

from dataclasses import dataclass

from japanmfa.domain import PhoneAnnotation
from japanmfa.errors import StageFailure
from .lexicon import LockedLexicon
from .textgrid import MfaAlignment, MfaPhone, MfaWord


@dataclass(frozen=True)
class RecoveryUnit:
    alias: str
    original_alias: str
    phones: tuple[str, ...]


def build_recovery_units(annotations: tuple[PhoneAnnotation, ...], lexicon: LockedLexicon) -> tuple[RecoveryUnit, ...]:
    """Group connected mora spans; a multi-mora phone always stays intact."""
    units: list[RecoveryUnit] = []
    for token, alias in zip(lexicon.tokens, lexicon.aliases):
        group: list[str] = []
        covered: set[int] = set()
        for item in annotations:
            if item.is_silence or item.token_index != token.index:
                continue
            indices = {m.index_in_token for m in item.morae}
            if not indices:
                raise StageFailure("recovery", "recovery_mapping_missing", "phone has no mora provenance")
            if group and not indices.intersection(covered):
                units.append(RecoveryUnit(f"jmfa_recovery_{len(units):06d}", alias, tuple(group)))
                group, covered = [], set()
            group.append(item.interval.label)
            covered.update(indices)
        if group:
            units.append(RecoveryUnit(f"jmfa_recovery_{len(units):06d}", alias, tuple(group)))
    return tuple(units)


def restore_recovery_alignment(alignment: MfaAlignment, units: tuple[RecoveryUnit, ...],
                               lexicon: LockedLexicon, offset: float) -> MfaAlignment:
    """Restore original token ownership and source time, checking every phone."""
    if tuple(w.alias for w in alignment.words) != tuple(u.alias for u in units):
        raise StageFailure("recovery", "recovery_alias_mismatch", "recovery aliases changed or are missing")
    aliases = {u.alias: u.original_alias for u in units}
    for unit in units:
        actual = tuple(p.label for p in alignment.phones if not p.is_silence and p.word_alias == unit.alias)
        if actual != unit.phones:
            raise StageFailure("recovery", "recovery_phone_mismatch", "recovery phone sequence differs from locked sequence")
    phones = tuple(MfaPhone(p.label, p.start + offset, p.end + offset,
                           None if p.is_silence else aliases[p.word_alias], p.is_silence)
                   for p in alignment.phones)
    words = []
    for alias in lexicon.aliases:
        group = [w for w in alignment.words if aliases[w.alias] == alias]
        if not group:
            raise StageFailure("recovery", "recovery_alias_mismatch", "original token omitted from recovery")
        words.append(MfaWord(alias, group[0].start + offset, group[-1].end + offset))
    return MfaAlignment(tuple(words), phones, ())
