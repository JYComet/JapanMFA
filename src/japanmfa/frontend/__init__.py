"""Japanese text frontend and occurrence-specific reading overrides."""

from .japanese import JapaneseFrontend, render_locked_kana
from .overrides import (
    ReadingOverride,
    ReadingOverrideSet,
    apply_reading_overrides,
    load_reading_overrides,
)

__all__ = [
    "JapaneseFrontend",
    "ReadingOverride",
    "ReadingOverrideSet",
    "apply_reading_overrides",
    "load_reading_overrides",
    "render_locked_kana",
]
