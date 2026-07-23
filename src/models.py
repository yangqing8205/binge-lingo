"""Data structures shared across modules."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class Expression:
    """A single learn-worthy English expression extracted from a screenshot."""

    expression: str          # the phrase/idiom/slang as it appears
    meaning_zh: str          # Chinese explanation
    scenario_zh: str         # when/how it's used, in Chinese
    original_line: str       # the original subtitle line, verbatim
    difficulty: str = ""     # 初级 / 中级 / 高级


@dataclass
class ScreenshotAnalysis:
    """Full result of analyzing one screenshot."""

    subtitle_text: str = ""                       # raw English text seen on screen
    expressions: List[Expression] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.expressions
