import re
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from japanmfa.domain import SourceText
from japanmfa.errors import SkipUtterance, StageFailure
from japanmfa.frontend import japanese
from japanmfa.frontend.japanese import JapaneseFrontend, render_locked_kana


@dataclass
class FakeMorpheme:
    text: str
    offset: int
    reading: str
    pos: tuple[str, ...]

    def surface(self) -> str:
        return self.text

    def begin(self) -> int:
        return self.offset

    def reading_form(self) -> str:
        return self.reading

    def part_of_speech(self) -> tuple[str, ...]:
        return self.pos


class FakeTokenizer:
    def __init__(self, rows: dict[str, list[FakeMorpheme]]) -> None:
        self.rows = rows
        self.modes: list[object] = []

    def tokenize(self, text: str, mode: object | None = None) -> list[FakeMorpheme]:
        if mode is not None:
            self.modes.append(mode)
        return self.rows[text]


class FakeDictionary:
    def __init__(self, tokenizer: FakeTokenizer, expected_mode: object) -> None:
        self.tokenizer = tokenizer
        self.expected_mode = expected_mode
        self.create_modes: list[object] = []

    def create(self, mode: object) -> FakeTokenizer:
        self.create_modes.append(mode)
        assert mode is self.expected_mode
        return self.tokenizer


@pytest.fixture
def frontend() -> JapaneseFrontend:
    mode_b = object()
    rows = {
        "今日は晴れ": [
            FakeMorpheme("今日", 0, "キョウ", ("名詞", "普通名詞")),
            FakeMorpheme("は", 2, "ハ", ("助詞",)),
            FakeMorpheme("晴れ", 3, "ハレ", ("名詞",)),
        ],
        "今日は晴れ。": [
            FakeMorpheme("今日", 0, "キョウ", ("名詞",)),
            FakeMorpheme("は", 2, "ハ", ("助詞",)),
            FakeMorpheme("晴れ", 3, "ハレ", ("名詞",)),
            FakeMorpheme("。", 5, "。", ("補助記号", "句点")),
        ],
        "今日は・晴れ": [
            FakeMorpheme("今日", 0, "キョウ", ("名詞",)),
            FakeMorpheme("は", 2, "ハ", ("助詞",)),
            FakeMorpheme("・", 3, "・", ("補助記号",)),
            FakeMorpheme("晴れ", 4, "ハレ", ("名詞",)),
        ],
        "がな": [
            FakeMorpheme("が", 0, "ガ", ("名詞",)),
            FakeMorpheme("な", 1, "ナ", ("名詞",)),
        ],
        "日本語★": [
            FakeMorpheme("日本語", 0, "ニホンゴ", ("名詞",)),
            FakeMorpheme("★", 3, "ホシ", ("記号",)),
        ],
        "日本語♪": [
            FakeMorpheme("日本語", 0, "ニホンゴ", ("名詞",)),
            FakeMorpheme("♪", 3, "オンプ", ("記号",)),
        ],
        "零": [FakeMorpheme("", 0, "", ("名詞",))],
        "2024年": [
            FakeMorpheme("2024", 0, "ニセンニジュウヨン", ("名詞", "数")),
            FakeMorpheme("年", 4, "ネン", ("名詞",)),
        ],
        "Tokyoへ行く": [
            FakeMorpheme("Tokyo", 0, "Tokyo", ("名詞",)),
            FakeMorpheme("へ", 5, "ヘ", ("助詞",)),
            FakeMorpheme("行く", 6, "イク", ("動詞",)),
        ],
        "hello": [FakeMorpheme("hello", 0, "hello", ("名詞",))],
        "日本語🙂": [
            FakeMorpheme("日本語", 0, "ニホンゴ", ("名詞",)),
            FakeMorpheme("🙂", 3, "🙂", ("補助記号",)),
        ],
    }
    tokenizer = FakeTokenizer(rows)
    dictionary = FakeDictionary(tokenizer, mode_b)
    module = SimpleNamespace(
        Dictionary=lambda **kwargs: (assert_core_dictionary(kwargs, dictionary)),
        SplitMode=SimpleNamespace(B=mode_b),
    )
    return JapaneseFrontend(sudachi_module=module)


def assert_core_dictionary(kwargs: dict[str, object], dictionary: FakeDictionary) -> FakeDictionary:
    assert kwargs == {"dict": "core"}
    return dictionary


def test_production_construction_reports_missing_sudachi_as_typed_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(name: str) -> object:
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(japanese.importlib, "import_module", missing)
    with pytest.raises(StageFailure) as exc_info:
        JapaneseFrontend()
    assert exc_info.value.stage == "frontend"
    assert exc_info.value.reason_code == "sudachi_unavailable"


def test_sudachi_mode_b_returns_locked_katakana(frontend: JapaneseFrontend) -> None:
    tokens = frontend.analyze(SourceText(original="今日は晴れ", processing="今日は晴れ", source="txt"))
    assert "".join(token.surface for token in tokens) == "今日は晴れ"
    assert all(re.fullmatch(r"[ァ-ヿー]+", token.reading) for token in tokens)
    assert [token.start for token in tokens] == [0, 2, 3]


def test_punctuation_is_preserved_in_spans_but_not_a_pronounced_token(
    frontend: JapaneseFrontend,
) -> None:
    tokens = frontend.analyze(
        SourceText(original="今日は晴れ。", processing="今日は晴れ。", source="txt")
    )
    assert "".join(token.surface for token in tokens) == "今日は晴れ"
    assert all(token.surface != "。" for token in tokens)
    assert render_locked_kana("今日は晴れ。", tokens) == "キョウハハレ。"


def test_middle_dot_punctuation_is_never_a_pronounced_token(frontend: JapaneseFrontend) -> None:
    tokens = frontend.analyze(
        SourceText(original="今日は・晴れ", processing="今日は・晴れ", source="txt")
    )
    assert "".join(token.surface for token in tokens) == "今日は晴れ"


@pytest.mark.parametrize("symbol", ["★", "♪"])
def test_unicode_symbols_are_skipped_even_with_a_katakana_reading(
    frontend: JapaneseFrontend, symbol: str
) -> None:
    text = f"日本語{symbol}"
    with pytest.raises(SkipUtterance, match="unsupported_japanese_text"):
        frontend.analyze(SourceText(original=text, processing=text, source="txt"))


def test_zero_length_morpheme_span_is_a_typed_failure(frontend: JapaneseFrontend) -> None:
    with pytest.raises(StageFailure) as exc_info:
        frontend.analyze(SourceText(original="零", processing="零", source="txt"))
    assert exc_info.value.reason_code == "token_span_mismatch"


def test_render_locked_kana_maps_processing_spans_to_original_and_preserves_linebreaks(
    frontend: JapaneseFrontend,
) -> None:
    original = " \r\n今日は\r\n晴れ  \r\n"
    processing = "今日は晴れ"
    tokens = frontend.analyze(SourceText(original=original, processing=processing, source="txt"))
    assert render_locked_kana(original, tokens) == " \r\nキョウハ\r\nハレ  \r\n"


def test_nfc_processing_maps_decomposed_original_clusters_and_preserves_gaps(
    frontend: JapaneseFrontend,
) -> None:
    original = " \r\nか\u3099な\r\n"
    tokens = frontend.analyze(
        SourceText(original=original, processing="か\u3099な", source="txt")
    )

    assert [(token.start, token.end, token.surface) for token in tokens] == [
        (0, 1, "が"),
        (1, 2, "な"),
    ]
    assert render_locked_kana(original, tokens) == " \r\nガナ\r\n"


def test_render_locked_kana_rejects_original_that_cannot_reproduce_processing(
    frontend: JapaneseFrontend,
) -> None:
    tokens = frontend.analyze(SourceText(original="今日は晴れ", processing="今日は晴れ", source="txt"))
    with pytest.raises(StageFailure) as exc_info:
        render_locked_kana("今日は曇り", tokens)
    assert exc_info.value.reason_code == "token_span_mismatch"


def test_numeric_token_with_katakana_reading_is_accepted(frontend: JapaneseFrontend) -> None:
    tokens = frontend.analyze(SourceText(original="2024年", processing="2024年", source="txt"))
    assert tokens[0].surface == "2024"
    assert tokens[0].reading == "ニセンニジュウヨン"


@pytest.mark.parametrize("text", ["Tokyoへ行く", "hello", "日本語🙂"])
def test_non_japanese_or_unknown_input_is_skipped(frontend: JapaneseFrontend, text: str) -> None:
    with pytest.raises(SkipUtterance, match="unsupported_japanese_text"):
        frontend.analyze(SourceText(original=text, processing=text, source="txt"))


def test_bad_token_span_is_a_typed_frontend_failure(frontend: JapaneseFrontend) -> None:
    frontend._tokenizer.rows["今日は晴れ"] = [  # type: ignore[attr-defined]
        FakeMorpheme("今日", 1, "キョウ", ("名詞",)),
    ]
    with pytest.raises(StageFailure) as exc_info:
        frontend.analyze(SourceText(original="今日は晴れ", processing="今日は晴れ", source="txt"))
    assert exc_info.value.stage == "frontend"
    assert exc_info.value.reason_code == "token_span_mismatch"


def test_render_locked_kana_rejects_overlapping_or_mismatched_token_spans(frontend: JapaneseFrontend) -> None:
    tokens = frontend.analyze(SourceText(original="今日は晴れ", processing="今日は晴れ", source="txt"))
    overlapping = (tokens[0], tokens[0].__class__(1, 1, 4, "日は", ("名詞",), "ヒハ", "sudachi"))
    with pytest.raises(StageFailure, match="token_span_mismatch"):
        render_locked_kana("今日は晴れ", overlapping)

    mismatched = (tokens[0].__class__(0, 0, 2, "別", ("名詞",), "ベツ", "sudachi"),)
    with pytest.raises(StageFailure, match="token_span_mismatch"):
        render_locked_kana("今日は晴れ", mismatched)


def test_japanese_wave_dash_is_preserved_as_punctuation() -> None:
    mode_b = object()
    tokenizer = FakeTokenizer({
        "世界～大丈夫": [
            FakeMorpheme("世界", 0, "セカイ", ("名詞",)),
            FakeMorpheme("～", 2, "～", ("補助記号",)),
            FakeMorpheme("大丈夫", 3, "ダイジョウブ", ("名詞",)),
        ]
    })
    dictionary = FakeDictionary(tokenizer, mode_b)
    module = SimpleNamespace(Dictionary=lambda **kwargs: dictionary, SplitMode=SimpleNamespace(B=mode_b))
    frontend = JapaneseFrontend(sudachi_module=module)
    source = SourceText("世界～大丈夫", "世界～大丈夫", "txt")
    tokens = frontend.analyze(source)
    assert [token.surface for token in tokens] == ["世界", "大丈夫"]
    assert render_locked_kana(source.original, tokens) == "セカイ～ダイジョウブ"
