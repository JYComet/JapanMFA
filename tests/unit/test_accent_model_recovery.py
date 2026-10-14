"""Recovery of invalid native accent marks requires exact lexical agreement."""

import pytest


def test_valid_native_marks_keep_the_original_path():
    from japanmfa.accent.model_recovery import needs_recovery

    assert needs_recovery("ア]ナ]タ", ("ア", "ナ", "タ"))
    assert not needs_recovery("ア[ナ]タ", ("ア", "ナ", "タ"))
    assert not needs_recovery("キ[カイガ]クシュー", ("キ", "カ", "イ", "ガ", "ク", "シュ", "ー"))


def test_exact_lexicon_and_constrained_model_agreement_recovers_real_word():
    from japanmfa.accent.model_recovery import choose_repair

    # Pinned model emits ア]ナ]タ; its best legal sequence is accent 2.
    logits = ((0.0, -7.0, -0.55), (0.0, -1.42, -11.0), (-3.0, 0.0, -9.0))
    result = choose_repair(
        "ア]ナ]タ", "あなた", "アナタ", ("ア", "ナ", "タ"), logits,
        ({"surface": "あなた", "kana": "アナタ", "acc": "2"},),
    )

    assert result == {"raw": "ア]ナ]タ", "marked": "ア[ナ]タ", "accent": 2,
                      "evidence": "exact_unidic_and_constrained_model"}


@pytest.mark.parametrize("marked,entries", [
    ("ア[ナ]タ", ({"surface": "あなた", "kana": "アナタ", "acc": "2"},)),
    ("ア]ナ]タ", ({"surface": "あなた", "kana": "アナタ", "acc": "1"},)),
    ("ア]ナ]タ", ({"surface": "あなた", "kana": "アナタ", "acc": "1,2"},)),
    ("ア]ナ]タ", ({"surface": "貴方", "kana": "アナタ", "acc": "2"},)),
    ("ア]ナ]タ", ({"surface": "あなた", "kana": "アナター", "acc": "2"},)),
    ("ア]ナ]タ", ({"surface": "あなた", "kana": "アナタ", "acc": "2"},
                   {"surface": "他", "kana": "タ", "acc": "1"})),
])
def test_repair_rejects_valid_or_unsubstantiated_output(marked, entries):
    from japanmfa.accent.model_recovery import choose_repair

    logits = ((0.0, -7.0, -0.55), (0.0, -1.42, -11.0), (-3.0, 0.0, -9.0))
    assert choose_repair(marked, "あなた", "アナタ", ("ア", "ナ", "タ"), logits, entries) is None


def test_repair_rejects_model_reading_mismatch():
    from japanmfa.accent.model_recovery import choose_repair

    logits = ((0.0, -7.0, -0.55), (0.0, -1.42, -11.0), (-3.0, 0.0, -9.0))
    assert choose_repair("ア]ナ]タ", "あなた", "アナター", ("ア", "ナ", "ター"), logits,
                         ({"surface": "あなた", "kana": "アナター", "acc": "2"},)) is None
