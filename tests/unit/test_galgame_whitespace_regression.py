import pytest
from japanmfa.domain import SourceText
from japanmfa.frontend.japanese import JapaneseFrontend

TEXTS = ['サワー サップ フレーバー ティーで、あとこのリコッタチーズケーキにかかってるのライモハニーよね。悪いんだけど、他のものに変えてくださる？\n', 'えっと、サワー サップ フレーバー ティーとリコタチーズケーキ、ケーキのライムハニーはジャムに変えるですね。\n', 'サワー サップ フレーバー ティーとリコッタチーズケーキ、十二番さんね。\n']

@pytest.mark.parametrize("original", TEXTS)
def test_internal_spaces_are_not_pronounced_morphemes(original):
    processing = original.replace("\r", "").replace("\n", "").strip()
    source = SourceText(original, processing, "txt")
    tokens = JapaneseFrontend().analyze(source)
    assert all(not t.surface.isspace() for t in tokens)
    assert all(t.reading != "キゴウ" for t in tokens)
    assert [t.index for t in tokens] == list(range(len(tokens)))
    assert all(original[t.start:t.end] == t.surface for t in tokens)
    assert source.original == original
