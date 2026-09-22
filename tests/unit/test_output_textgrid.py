from pathlib import Path

from japanmfa.domain import Mora, PhoneAnnotation, PhoneInterval
from japanmfa.output.textgrid import (
    validate_five_tier_textgrid,
    write_five_tier_textgrid,
)


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
