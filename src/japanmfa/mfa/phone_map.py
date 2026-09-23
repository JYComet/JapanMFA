"""Strict, versioned kana-to-phone rules for the pinned Japanese MFA model."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from japanmfa.errors import StageFailure


EXPECTED_MODEL_FAMILY = "japanese_mfa_v3"


def _failure(reason_code: str, message: str, **details: object) -> StageFailure:
    return StageFailure("projection", reason_code, message, details)


class _UniqueLoader(yaml.SafeLoader):
    """SafeLoader variant that does not silently discard duplicate YAML keys."""


def _construct_unique_mapping(loader: _UniqueLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping", node.start_mark, f"duplicate key: {key!r}", key_node.start_mark
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


@dataclass(frozen=True)
class PhoneRule:
    """One exact contiguous mora pattern and its exact phone pattern."""

    kana: tuple[str, ...]
    phones: tuple[str, ...]
    # Half-open indices into ``kana`` for each output phone.  The explicit
    # spans are what distinguish a one-to-one sequence from a phone that
    # covers multiple morae (or a mora repeated over several phones).
    mora_spans: tuple[tuple[int, int], ...]
    cost: int = 0


@dataclass(frozen=True)
class PhoneMap:
    """Validated model-family-specific phone rules and explicit aliases."""

    model_family: str
    normalizations: tuple[tuple[str, str], ...]
    rules: tuple[PhoneRule, ...]

    @classmethod
    def load(
        cls,
        path: Path,
    ) -> "PhoneMap":
        path = Path(path)
        try:
            with path.open("r", encoding="utf-8") as stream:
                raw = yaml.load(stream, Loader=_UniqueLoader)
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            raise _failure(
                "phone_map_read_failed",
                f"could not load phone map: {path}",
                path=str(path),
                error=str(exc),
            ) from exc

        if not isinstance(raw, Mapping):
            raise _failure("invalid_phone_map", "phone map root must be a mapping", path=str(path))
        unknown = set(raw) - {"model_family", "normalizations", "rules"}
        if unknown:
            raise _failure(
                "unknown_field",
                "phone map contains unknown top-level fields",
                fields=sorted(str(item) for item in unknown),
            )
        configured = raw.get("model_family")
        if configured != EXPECTED_MODEL_FAMILY:
            raise _failure(
                "model_family_mismatch",
                f"phone map model family must be {EXPECTED_MODEL_FAMILY!r}",
                configured=configured,
                expected=EXPECTED_MODEL_FAMILY,
            )

        normalizations = _parse_normalizations(raw.get("normalizations", {}))
        rules = _parse_rules(raw.get("rules"), normalizations)
        return cls(EXPECTED_MODEL_FAMILY, tuple(normalizations.items()), tuple(rules))

    @property
    def normalization_aliases(self) -> Mapping[str, str]:
        return dict(self.normalizations)

    @property
    def known_phones(self) -> frozenset[str]:
        return frozenset(phone for rule in self.rules for phone in rule.phones)

    def normalize(self, phone: str) -> str:
        """Apply one explicitly configured alias; no IPA modifier stripping occurs."""
        return dict(self.normalizations).get(phone, phone)

    def rule_for(self, kana: tuple[str, ...], phones: tuple[str, ...]) -> PhoneRule:
        normalized = tuple(self.normalize(phone) for phone in phones)
        for rule in self.rules:
            if rule.kana == tuple(kana) and rule.phones == normalized:
                return rule
        raise KeyError((tuple(kana), normalized))


def _parse_normalizations(raw: object) -> dict[str, str]:
    if not isinstance(raw, Mapping):
        raise _failure("invalid_normalizations", "normalizations must be a mapping")
    result: dict[str, str] = {}
    for source, target in raw.items():
        if not isinstance(source, str) or not source or not isinstance(target, str) or not target:
            raise _failure(
                "invalid_normalizations",
                "normalization aliases must map non-empty strings to non-empty strings",
            )
        result[source] = target
    return result


def _parse_rules(raw: object, normalizations: Mapping[str, str]) -> list[PhoneRule]:
    if not isinstance(raw, list) or not raw:
        raise _failure("invalid_rules", "rules must be a non-empty array")
    rules: list[PhoneRule] = []
    seen: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise _failure("invalid_rule", "each phone-map rule must be a mapping", index=index)
        unknown = set(item) - {"kana", "phones", "mora_spans", "cost"}
        if unknown:
            raise _failure(
                "unknown_rule_field",
                "phone-map rule contains unknown fields",
                index=index,
                fields=sorted(str(value) for value in unknown),
            )
        kana = item.get("kana")
        if isinstance(kana, str):
            kana_tuple = (kana,)
        elif isinstance(kana, list) and all(isinstance(value, str) and value for value in kana):
            kana_tuple = tuple(kana)
        else:
            raise _failure("invalid_rule", "rule kana must be a non-empty string array", index=index)
        phones = item.get("phones")
        if not isinstance(phones, list) or not phones or not all(
            isinstance(value, str) and value for value in phones
        ):
            raise _failure("invalid_rule", "rule phones must be a non-empty string array", index=index)
        phones_tuple = tuple(normalizations.get(phone, phone) for phone in phones)
        mora_spans = _parse_mora_spans(
            item.get("mora_spans"), len(kana_tuple), len(phones_tuple), index
        )
        cost = item.get("cost", 0)
        if isinstance(cost, bool) or not isinstance(cost, int) or cost < 0:
            raise _failure("invalid_rule", "rule cost must be a non-negative integer", index=index)
        identity = (kana_tuple, phones_tuple)
        if identity in seen:
            raise _failure("duplicate_rule", "phone-map rules must be unique", index=index)
        seen.add(identity)
        rules.append(PhoneRule(kana_tuple, phones_tuple, mora_spans, cost))
    return rules


def _parse_mora_spans(
    raw: object, kana_count: int, phone_count: int, index: int
) -> tuple[tuple[int, int], ...]:
    """Validate or infer each phone's half-open mora range.

    The only implicit many-to-many cases are unambiguous cardinality cases:
    one mora to many phones and many morae to one phone.  A rule with more
    than one item on both sides and unequal lengths must declare spans so we
    never guess how the alignment should be projected.
    """
    if raw is None:
        if kana_count == phone_count:
            return tuple((position, position + 1) for position in range(kana_count))
        if kana_count == 1:
            return ((0, 1),) * phone_count
        if phone_count == 1:
            return ((0, kana_count),)
        raise _failure(
            "invalid_rule",
            "multi-mora/multi-phone rules with unequal lengths require mora_spans",
            index=index,
        )

    if not isinstance(raw, list) or len(raw) != phone_count:
        raise _failure(
            "invalid_rule",
            "mora_spans must contain one [start, end] range per phone",
            index=index,
        )
    spans: list[tuple[int, int]] = []
    for span in raw:
        if (
            not isinstance(span, list)
            or len(span) != 2
            or any(isinstance(value, bool) or not isinstance(value, int) for value in span)
        ):
            raise _failure(
                "invalid_rule",
                "each mora_spans item must be an integer [start, end] pair",
                index=index,
            )
        start, end = span
        if not 0 <= start < end <= kana_count:
            raise _failure(
                "invalid_rule",
                "mora_spans ranges must be non-empty and within the kana pattern",
                index=index,
            )
        spans.append((start, end))

    if spans[0][0] != 0 or spans[-1][1] != kana_count:
        raise _failure(
            "invalid_rule",
            "mora_spans must cover the complete kana pattern in phone order",
            index=index,
        )
    if any(
        previous[0] > current[0]
        or previous[1] < current[0]
        or previous[1] > current[1]
        for previous, current in zip(spans, spans[1:])
    ):
        raise _failure(
            "invalid_rule",
            "mora_spans must be ordered and gap-free in phone order",
            index=index,
        )
    return tuple(spans)


__all__ = ["EXPECTED_MODEL_FAMILY", "PhoneMap", "PhoneRule"]
