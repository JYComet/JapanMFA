from pathlib import Path

from japanmfa.domain import Mora, PhoneAnnotation, PhoneInterval
from japanmfa.output.textgrid import (
    validate_five_tier_textgrid,
    write_five_tier_textgrid,
)
from japanmfa.output import textgrid as textgrid_module


def _annotations() -> tuple[PhoneAnnotation, ...]:
    mora = Mora(0, 0, "カ", "H")
    return (
        PhoneAnnotation(PhoneInterval(0.0, 0.25, "k"), 0, (mora,), "カ", "H", False),
        PhoneAnnotation(PhoneInterval(0.25, 0.5, "a"), 0, (mora,), "カ", "H", False),
        PhoneAnnotation(PhoneInterval(0.5, 0.75, "sp"), None, (), "", "", True),
        PhoneAnnotation(
            PhoneInterval(0.75, 1.25, "aː"),
            0,
            (Mora(0, 1, "ア", "H"), Mora(0, 2, "ア", "L")),
            "ア|ア",
            "H|L",
            False,
        ),
    )


def test_writes_validated_five_tier_textgrid_with_shared_phone_boundaries(
    tmp_path: Path,
) -> None:
    path = tmp_path / "alignment.TextGrid"

    write_five_tier_textgrid(path, 1.25, "カア", "カア", _annotations())
    validate_five_tier_textgrid(path, 1.25, frozenset({"sp"}))

    text = path.read_text(encoding="utf-8")
    names = [line.strip().split("=", 1)[1].strip() for line in text.splitlines() if line.strip().startswith("name =")]
    assert names == ['"original"', '"kana"', '"phones"', '"phone_kana"', '"phone_tone"']

    blocks = text.split('name = "')
    lower = [block.split("\n", 1)[1] for block in blocks if block.startswith(("phones\"", "phone_kana\"", "phone_tone\""))]
    boundaries = [
        [(line.split("=", 1)[1].strip()) for line in block.splitlines() if line.strip().startswith(("xmin =", "xmax ="))]
        for block in lower
    ]
    assert boundaries[0] == boundaries[1] == boundaries[2]


def test_textgrid_round_trips_quotes_with_praat_doubled_quote_syntax(tmp_path: Path) -> None:
    path = tmp_path / "quoted.TextGrid"
    annotation = PhoneAnnotation(
        PhoneInterval(0.0, 1.0, 'p"q'),
        0,
        (Mora(0, 0, 'カ"', "H"),),
        'カ"',
        "H",
        False,
    )

    write_five_tier_textgrid(path, 1.0, '原"文', 'カ"ナ', (annotation,))
    validate_five_tier_textgrid(path, 1.0, frozenset())

    text = path.read_text(encoding="utf-8")
    assert 'text = "原""文"' in text
    assert 'text = "p""q"' in text
    assert '\\"' not in text


def test_textgrid_round_trips_multiline_original_with_crlf_and_trailing_newline(
    tmp_path: Path,
) -> None:
    path = tmp_path / "multiline-original.TextGrid"
    original = '第一行\r\n第二行\n末尾\n"引号"\r\n'

    write_five_tier_textgrid(path, 1.0, original, "カナ", (_annotations()[0],))
    validate_five_tier_textgrid(path, 1.0, frozenset())

    _, _, tiers = textgrid_module._parse(path)
    assert tiers[0].intervals[0].label == original


def test_textgrid_rejects_wrong_declared_tier_size(tmp_path: Path) -> None:
    path = tmp_path / "wrong-size.TextGrid"
    write_five_tier_textgrid(path, 1.0, "原", "カ", _annotations()[:1])
    path.write_text(path.read_text(encoding="utf-8").replace("size = 5", "size = 4", 1), encoding="utf-8")

    import pytest

    with pytest.raises(ValueError, match="declared tier size"):
        validate_five_tier_textgrid(path, 1.0, frozenset())
