"""Typed definitions for splitter strategies and their configuration."""

from __future__ import annotations

from enum import StrEnum
from typing import Dict, Type

from pydantic import BaseModel, Field, PositiveInt, model_validator


class SplitStrategyType(StrEnum):
    """Supported text splitting strategies."""

    CHARACTER_COUNT = "character_count"
    CHAPTER_KEYWORD = "chapter_keyword"
    RATIO = "ratio"
    FIXED_COUNT = "fixed_count"


DEFAULT_CHAPTER_PATTERN = (
    r"(?im)^(?:chapter|section|part)\b[\s:.-]*(?:\d+|[ivxlcdm]+)|"  # English headings
    r"(?m)^第[\d一二三四五六七八九十百千零〇两]+[章节回篇部集]"  # Chinese chapter style
)


class CharacterCountParameters(BaseModel):
    """Configuration for character-count based splitting."""

    max_characters: PositiveInt = Field(
        ..., description="Maximum number of characters per segment"
    )


class ChapterKeywordParameters(BaseModel):
    """Configuration for chapter keyword based splitting."""

    pattern: str = Field(
        default=DEFAULT_CHAPTER_PATTERN,
        description="Regular expression used to identify chapter boundaries",
    )
    fallback_max_characters: PositiveInt | None = Field(
        default=None,
        description="Optional maximum characters used when pattern matches are insufficient",
    )


class RatioParameters(BaseModel):
    """Configuration for ratio based splitting."""

    ratios: list[float] = Field(
        ...,
        min_items=1,
        description="Relative ratios determining segment lengths",
    )

    @model_validator(mode="after")
    def _validate_ratios(self) -> "RatioParameters":
        if any(r <= 0 for r in self.ratios):
            raise ValueError("All ratios must be positive numbers")
        return self


class FixedCountParameters(BaseModel):
    """Configuration for fixed-count splitting."""

    segments: PositiveInt = Field(
        ..., description="Number of segments to produce"
    )


StrategyParameter = CharacterCountParameters | ChapterKeywordParameters | RatioParameters | FixedCountParameters


_PARAMETER_MODELS: Dict[SplitStrategyType, Type[BaseModel]] = {
    SplitStrategyType.CHARACTER_COUNT: CharacterCountParameters,
    SplitStrategyType.CHAPTER_KEYWORD: ChapterKeywordParameters,
    SplitStrategyType.RATIO: RatioParameters,
    SplitStrategyType.FIXED_COUNT: FixedCountParameters,
}


def parse_strategy_parameters(
    strategy: SplitStrategyType, parameters: dict
) -> StrategyParameter:
    """Validate and coerce raw strategy parameters into typed configuration models."""

    model = _PARAMETER_MODELS.get(strategy)
    if model is None:
        raise ValueError(f"Unsupported strategy '{strategy}'")
    return model.model_validate(parameters or {})


__all__ = [
    "SplitStrategyType",
    "DEFAULT_CHAPTER_PATTERN",
    "CharacterCountParameters",
    "ChapterKeywordParameters",
    "RatioParameters",
    "FixedCountParameters",
    "StrategyParameter",
    "parse_strategy_parameters",
]
