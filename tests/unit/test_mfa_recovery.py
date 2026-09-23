import pytest

from japanmfa.domain import Mora, PhoneAnnotation, PhoneInterval, Pronunciation, Token
from japanmfa.mfa.lexicon import LockedLexicon
from japanmfa.mfa.recovery import build_recovery_units, restore_recovery_alignment
from japanmfa.mfa.textgrid import MfaAlignment, MfaPhone, MfaWord
from japanmfa.errors import StageFailure


def test_recovery_groups_shared_mora_phones_and_never_splits_long_phone() -> None:
    token = Token(0, 0, 3, "ハオー", (), "ハオー", "override")
    lex = LockedLexicon.build("x", (token,), (Pronunciation("ハオー", ("h", "a", "oː")),))
    a, b, c = Mora(0, 0, "ハ", "L"), Mora(0, 1, "オ", "H"), Mora(0, 2, "ー", "L")
    annotations = tuple(PhoneAnnotation(PhoneInterval(i / 3, (i + 1) / 3, p), 0, ms, "", "", False) for i, (p, ms) in enumerate((("h", (a,)), ("a", (a,)), ("oː", (b, c)))))
    units = build_recovery_units(annotations, lex)
    assert [u.phones for u in units] == [("h", "a"), ("oː",)]
    alignment = MfaAlignment(tuple(MfaWord(u.alias, i / 2, (i + 1) / 2) for i, u in enumerate(units)),
        (MfaPhone("h", 0, .1, units[0].alias, False), MfaPhone("a", .1, .5, units[0].alias, False), MfaPhone("oː", .5, 1., units[1].alias, False)), ())
    restored = restore_recovery_alignment(alignment, units, lex, .2)
    assert [w.alias for w in restored.words] == ["jmfa_000000"]
    assert [p.label for p in restored.phones] == ["h", "a", "oː"]
    assert [p.start for p in restored.phones] == pytest.approx([.2, .3, .7])
    assert [p.end for p in restored.phones] == pytest.approx([.3, .7, 1.2])
    assert all(p.word_alias == "jmfa_000000" for p in restored.phones)
    bad = MfaAlignment(alignment.words, alignment.phones[:-1], ())
    with pytest.raises(StageFailure, match="phone sequence"):
        restore_recovery_alignment(bad, units, lex, .2)
