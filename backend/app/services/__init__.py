"""Domain services for the backend application."""

from .splitting import (
    SplitStrategy,
    split_by_character_count,
    split_by_fixed_chapters,
    split_by_keywords,
    split_by_ratio,
)

__all__ = [
    "SplitStrategy",
    "split_by_character_count",
    "split_by_fixed_chapters",
    "split_by_keywords",
    "split_by_ratio",
]
