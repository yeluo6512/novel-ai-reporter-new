"""Request and response models for splitter endpoints."""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field, field_validator

from app.core.splitter.types import SplitStrategyType


class SplitRequest(BaseModel):
    """Common payload for requesting a split preview."""

    project_id: str = Field(..., description="Identifier of the project to associate the split with")
    text: str = Field(..., description="Raw text content to split")
    strategy: SplitStrategyType = Field(..., description="Splitting strategy to apply")
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional strategy-specific configuration parameters",
    )

    @field_validator("project_id")
    @classmethod
    def _strip_project_id(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("project_id cannot be blank")
        return trimmed


class SplitExecuteRequest(SplitRequest):
    """Payload for executing a split and persisting outputs."""

    overwrite: bool = Field(
        default=False,
        description="Whether existing split artefacts may be overwritten",
    )


class SegmentPreview(BaseModel):
    """Preview representation of a single segment."""

    index: int = Field(..., description="Segment ordinal index starting at 1")
    start_offset: int = Field(..., ge=0, description="Inclusive character offset of the segment start")
    end_offset: int = Field(..., ge=0, description="Exclusive character offset of the segment end")
    byte_start_offset: int = Field(..., ge=0, description="Inclusive byte offset relative to UTF-8 encoding")
    byte_end_offset: int = Field(..., ge=0, description="Exclusive byte offset relative to UTF-8 encoding")
    character_count: int = Field(..., ge=0, description="Number of Unicode codepoints in the segment")
    byte_count: int = Field(..., ge=0, description="Number of UTF-8 bytes in the segment")


class SplitPreviewResponse(BaseModel):
    """Response payload for split preview operations."""

    project_id: str = Field(...)
    strategy: SplitStrategyType = Field(...)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    total_segments: int = Field(..., ge=0)
    total_characters: int = Field(..., ge=0)
    total_bytes: int = Field(..., ge=0)
    source_sha256: str = Field(..., min_length=64, max_length=64)
    segments: List[SegmentPreview] = Field(default_factory=list)


class SplitExecutionResponse(SplitPreviewResponse):
    """Response payload for split execution operations."""

    output_directory: str = Field(..., description="Filesystem directory containing generated segment files")
    metadata_path: str = Field(..., description="Path to the stored metadata JSON file")
    written_files: List[str] = Field(..., description="List of segment filenames that were written")


__all__ = [
    "SplitRequest",
    "SplitExecuteRequest",
    "SplitPreviewResponse",
    "SplitExecutionResponse",
    "SegmentPreview",
]
