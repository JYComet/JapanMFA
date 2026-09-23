from pathlib import Path

import pytest
from praatio import textgrid as praat_textgrid

from japanmfa.domain import Mora, PhoneAnnotation, PhoneInterval
from japanmfa.output.textgrid import (
    validate_five_tier_textgrid,
    write_five_tier_textgrid,
)
from japanmfa.output import textgrid as textgrid_module


def _annotations() -> tuple[PhoneAnnotation, ...]:
    mora = Mora(0, 0, "カ", "H")
    return (
        PhoneAnnotation(PhoneInterval(0.0, 0.25, "k"), 0, (mora,), "カ", "HH", False),
        PhoneAnnotation(PhoneInterval(0.25, 0.5, "a"), 0, (mora,), "カ", "HH", False),
        PhoneAnnotation(PhoneInterval(0.5, 0.75, "sp"), None, (), "", "", True),
        PhoneAnnotation(
            PhoneInterval(0.75, 1.25, "aː"),
            0,
            (Mora(0, 1, "ア", "H"), Mora(0, 2, "ア", "L")),
            "ア|ア",
            "HL",
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
        "HH",
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


def test_export_explicitly_partitions_leading_internal_and_trailing_silence(tmp_path: Path) -> None:
    path = tmp_path / "gaps.TextGrid"
    mora = Mora(0, 0, "ア", "H")
    annotations = tuple(PhoneAnnotation(PhoneInterval(s, e, "a"), 0, (mora,), "ア", "HH", False) for s, e in ((.2, .4), (.7, .9)))
    write_five_tier_textgrid(path, 1.2, "ああ", "アア", annotations)
    grid = praat_textgrid.openTextgrid(str(path), includeEmptyIntervals=True)
    for name in ("phones", "phone_kana", "phone_tone"):
        rows = grid.getTier(name).entries
        assert [(r.start, r.end) for r in rows] == [(0., .2), (.2, .4), (.4, .7), (.7, .9), (.9, 1.2)]
        assert [r.label for r in rows[::2]] == ["", "", ""]
    validate_five_tier_textgrid(path, 1.2, frozenset())


def test_validator_rejects_missing_edge_intervals(tmp_path: Path) -> None:
    path = tmp_path / "incomplete.TextGrid"
    tiers = (("original", (("0.0", "1.0", "あ"),)), ("kana", (("0.0", "1.0", "ア"),)),
             ("phones", (("0.2", "0.8", "a"),)), ("phone_kana", (("0.2", "0.8", "ア"),)), ("phone_tone", (("0.2", "0.8", "HH"),)))
    path.write_text(textgrid_module._render(1.0, tiers), encoding="utf-8")
    with pytest.raises(ValueError, match="partition|cover|gap"):
        validate_five_tier_textgrid(path, 1.0, frozenset())


@pytest.mark.parametrize("tone", ["H", "L", "H|L", "HLH", "XX"])
def test_export_rejects_noncanonical_phone_contours(tmp_path: Path, tone: str) -> None:
    annotation = PhoneAnnotation(PhoneInterval(0., 1., "a"), 0, (Mora(0, 0, "ア", "H"),), "ア", tone, False)
    with pytest.raises(ValueError, match="tone|contour"):
        write_five_tier_textgrid(tmp_path / "invalid.TextGrid", 1., "あ", "ア", (annotation,))
