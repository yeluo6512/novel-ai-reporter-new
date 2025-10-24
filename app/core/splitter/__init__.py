"""Public interface for the splitter service."""

from .exceptions import (
    InvalidStrategyError,
    ProjectPathError,
    SplitExecutionError,
    SplitterError,
    StrategyConfigurationError,
)
from .service import SegmentStats, SplitExecutionResult, SplitPreviewResult, SplitterService
from .types import (
    DEFAULT_CHAPTER_PATTERN,
    SplitStrategyType,
    parse_strategy_parameters,
)

__all__ = [
    "SplitterService",
    "SplitPreviewResult",
    "SplitExecutionResult",
    "SegmentStats",
    "SplitStrategyType",
    "DEFAULT_CHAPTER_PATTERN",
    "parse_strategy_parameters",
    "SplitterError",
    "InvalidStrategyError",
    "StrategyConfigurationError",
    "ProjectPathError",
    "SplitExecutionError",
]
