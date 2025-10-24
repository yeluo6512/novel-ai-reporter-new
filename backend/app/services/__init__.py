"""Domain services for the backend application."""

from .pipeline import (
    AIInvokeConfig,
    PipelineError,
    PromptDefinitionData,
    SegmentInput,
    SegmentProcessingResult,
    SegmentRetryResult,
    SegmentSummary,
    invoke_ai_response,
    process_segments,
    retry_segment,
)
from .splitting import (
    SplitStrategy,
    split_by_character_count,
    split_by_fixed_chapters,
    split_by_keywords,
    split_by_ratio,
)

__all__ = [
    "AIInvokeConfig",
    "PipelineError",
    "PromptDefinitionData",
    "SegmentInput",
    "SegmentProcessingResult",
    "SegmentRetryResult",
    "SegmentSummary",
    "SplitStrategy",
    "invoke_ai_response",
    "process_segments",
    "retry_segment",
    "split_by_character_count",
    "split_by_fixed_chapters",
    "split_by_keywords",
    "split_by_ratio",
]
