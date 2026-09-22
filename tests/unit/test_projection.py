from __future__ import annotations

from pathlib import Path

import pytest

from japanmfa.domain import Mora, PhoneInterval, Pronunciation, Token
from japanmfa.errors import StageFailure
from japanmfa.mfa.lexicon import LockedLexicon
from japanmfa.mfa.phone_map import PhoneMap
from japanmfa.mfa.textgrid import MfaAlignment, MfaPhone, MfaWord
from japanmfa.projection import labels_for_phone, project_annotations


PHONE_MAP = PhoneMap.load(
    Path(__file__).parents[2]
    / "src"
    / "japanmfa"
    / "mfa"
    / "data"
    / "japanese_mfa_v3_phone_map.yaml"
)


def _lexicon(reading: str, phones: tuple[str, ...]) -> LockedLexicon:
    token = Token(0, 0, len(reading), reading, ("名詞",), reading, "override")
    return LockedLexicon.build("utt", (token,), (Pronunciation(reading, phones),))


def _alignment(phone_rows: tuple[tuple[str, float, float, bool], ...]) -> MfaAlignment:
    return MfaAlignment(
        words=(MfaWord("jmfa_000000", 0.0, 1.0),),
        phones=tuple(
            MfaPhone(label, start, end, None if silence else "jmfa_000000", silence)
            for label, start, end, silence in phone_rows
        ),
        diagnostic_intervals=(),
    )


def _morae(*items: tuple[str, str]) -> tuple[Mora, ...]:
    return tuple(Mora(0, index, kana, tone) for index, (kana, tone) in enumerate(items))


def test_projection_repeats_one_mora_label_for_multiple_cv_phones() -> None:
    lexicon = _lexicon("カ", ("k", "a"))
    alignment = _alignment((("k", 0.0, 0.2, False), ("a", 0.2, 0.4, False)))

    annotations = project_annotations(alignment, lexicon, {0: _morae(("カ", "H"))}, PHONE_MAP)

    assert [(item.kana_label, item.tone_label, item.interval.start, item.interval.end) for item in annotations] == [
        ("カ", "H", 0.0, 0.2),
        ("カ", "H", 0.2, 0.4),
    ]
    assert all(item.morae == _morae(("カ", "H")) for item in annotations)


def test_projection_keeps_one_long_phone_boundary_and_composes_mora_tones() -> None:
    lexicon = _lexicon("オー", ("oː",))
    alignment = _alignment((("oː", 0.25, 0.75, False),))

    annotations = project_annotations(
        alignment, lexicon, {0: _morae(("オ", "H"), ("ー", "L"))}, PHONE_MAP
    )

    assert len(annotations) == 1
    assert annotations[0].interval == PhoneInterval(0.25, 0.75, "oː")
    assert annotations[0].kana_label == "オ|ー"
    assert annotations[0].tone_label == "H|L"


def test_projection_supports_palatalized_mora_n_and_sokuon() -> None:
    cases = (
        ("キョ", ("k", "jo"), ("キョ",)),
        ("ン", ("N",), ("ン",)),
        ("ッ", ("Q",), ("ッ",)),
    )
    for reading, phones, kana in cases:
        lexicon = _lexicon(reading, phones)
        alignment = _alignment(tuple((phone, index * 0.1, (index + 1) * 0.1, False) for index, phone in enumerate(phones)))
        annotations = project_annotations(alignment, lexicon, {0: _morae((kana[0], "L"))}, PHONE_MAP)
        assert [item.kana_label for item in annotations] == [kana[0]] * len(phones)
        assert [item.tone_label for item in annotations] == ["L"] * len(phones)


def test_projection_reconciles_palatalized_word_with_following_vowel() -> None:
    lexicon = _lexicon("キョウ", ("k", "jo", "u"))
    alignment = _alignment(
        (("k", 0.0, 0.1, False), ("jo", 0.1, 0.2, False), ("u", 0.2, 0.3, False))
    )

    annotations = project_annotations(
        alignment,
        lexicon,
        {0: _morae(("キョ", "H"), ("ウ", "L"))},
        PHONE_MAP,
    )

    assert [item.kana_label for item in annotations] == ["キョ", "キョ", "ウ"]
    assert [item.tone_label for item in annotations] == ["H", "H", "L"]


def test_projection_reconciles_explicit_devoiced_vowel_spelling() -> None:
    lexicon = _lexicon("ス", ("s", "ɯ̥"))
    alignment = _alignment((("s", 0.0, 0.1, False), ("ɯ̥", 0.1, 0.2, False)))

    annotations = project_annotations(
        alignment, lexicon, {0: _morae(("ス", "L"))}, PHONE_MAP
    )

    assert [item.kana_label for item in annotations] == ["ス", "ス"]
    assert [item.tone_label for item in annotations] == ["L", "L"]


def test_projection_emits_silence_with_blank_labels_and_no_token() -> None:
    lexicon = _lexicon("ア", ("a",))
    alignment = _alignment((("sil", 0.0, 0.1, True), ("a", 0.1, 0.2, False)))

    annotations = project_annotations(alignment, lexicon, {0: _morae(("ア", "H"))}, PHONE_MAP)

    assert annotations[0].is_silence
    assert annotations[0].token_index is None
    assert annotations[0].kana_label == ""
    assert annotations[0].tone_label == ""
    assert annotations[1].token_index == 0


def test_projection_rejects_ambiguous_lowest_cost_mapping(tmp_path: Path) -> None:
    path = tmp_path / "ambiguous.yaml"
    path.write_text(
        """
model_family: japanese_mfa_v3
normalizations: {}
rules:
  - kana: [ア]
    phones: [a]
  - kana: [ー]
    phones: [a]
  - kana: [ア, ー]
    phones: [a, a]
""",
        encoding="utf-8",
    )
    phone_map = PhoneMap.load(path)
    lexicon = _lexicon("アー", ("a", "a"))
    alignment = MfaAlignment(
        words=(MfaWord("jmfa_000000", 0.0, 1.0),),
        phones=(
            MfaPhone("a", 0.0, 0.5, "jmfa_000000", False),
            MfaPhone("a", 0.5, 1.0, "jmfa_000000", False),
        ),
        diagnostic_intervals=(),
    )

    with pytest.raises(StageFailure) as exc_info:
        project_annotations(alignment, lexicon, {0: _morae(("ア", "H"), ("ー", "L"))}, phone_map)

    assert (exc_info.value.stage, exc_info.value.reason_code) == (
        "projection",
        "ambiguous_mora_phone_mapping",
    )


def test_projection_requires_exact_alias_order_and_phone_sequence() -> None:
    lexicon = _lexicon("ア", ("a",))
    bad_aliases = MfaAlignment(
        words=(MfaWord("wrong", 0.0, 1.0),), phones=(), diagnostic_intervals=()
    )
    with pytest.raises(StageFailure) as exc_info:
        project_annotations(bad_aliases, lexicon, {0: _morae(("ア", "H"))}, PHONE_MAP)
    assert exc_info.value.reason_code == "word_alias_mismatch"

    bad_phones = _alignment((("e", 0.0, 1.0, False),))
    with pytest.raises(StageFailure) as exc_info:
        project_annotations(bad_phones, lexicon, {0: _morae(("ア", "H"))}, PHONE_MAP)
    assert exc_info.value.reason_code == "phone_sequence_mismatch"


def test_projection_rejects_mora_kana_that_does_not_reconstruct_locked_reading() -> None:
    lexicon = _lexicon("ア", ("a",))
    alignment = _alignment((("a", 0.0, 1.0, False),))

    with pytest.raises(StageFailure) as exc_info:
        project_annotations(alignment, lexicon, {0: _morae(("イ", "H"))}, PHONE_MAP)

    assert exc_info.value.reason_code == "mora_reading_mismatch"


def test_projection_rejects_mora_order_that_does_not_reconstruct_locked_reading() -> None:
    token = Token(0, 0, 2, "アカ", ("名詞",), "アカ", "override")
    lexicon = LockedLexicon.build("utt", (token,), (Pronunciation("アカ", ("k", "a")),))
    alignment = _alignment((("k", 0.0, 0.5, False), ("a", 0.5, 1.0, False)))

    with pytest.raises(StageFailure) as exc_info:
        project_annotations(
            alignment,
            lexicon,
            {0: _morae(("カ", "H"), ("ア", "L"))},
            PHONE_MAP,
        )

    assert exc_info.value.reason_code == "mora_reading_mismatch"


def test_labels_for_phone_rejects_unlabeled_mora() -> None:
    with pytest.raises(StageFailure) as exc_info:
        labels_for_phone((Mora(0, 0, "ア", None),))
    assert exc_info.value.reason_code == "unlabeled_phone"
