"""Models related to orchestration workflows and background task status."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Sequence

from pydantic import BaseModel, Field


class StageName(str, Enum):
    """Canonical stage identifiers for the orchestration pipeline."""

    ANALYSIS = "analysis"
    INTEGRATION = "integration"
    FINALIZATION = "finalization"


class TaskState(str, Enum):
    """High-level execution states used for tracking progress."""

    IDLE = "idle"
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class StageStatus(BaseModel):
    """Status information for a single pipeline stage."""

    stage: StageName = Field(..., description="Stage identifier")
    status: TaskState = Field(..., description="Current execution state for the stage")
    detail: str | None = Field(
        default=None, description="Human-readable detail or progress message"
    )
    started_at: datetime | None = Field(
        default=None, description="UTC timestamp when the stage started"
    )
    completed_at: datetime | None = Field(
        default=None, description="UTC timestamp when the stage completed"
    )


class OrchestrationStatus(BaseModel):
    """Aggregated status for an orchestration cycle."""

    project_id: str = Field(..., description="Identifier for the project workspace")
    status: TaskState = Field(..., description="Overall state of the orchestration task")
    stages: List[StageStatus] = Field(
        default_factory=list, description="Ordered statuses for each pipeline stage"
    )
    message: str | None = Field(
        default=None, description="Summary message describing the current state"
    )
    requested_segments: Sequence[int] | None = Field(
        default=None,
        description="Optional set of segment indices requested for regeneration",
    )
    cascade: bool | None = Field(
        default=None,
        description="Indicates if cascading updates were requested for this run",
    )
    updated_at: datetime = Field(
        ...,
        description="UTC timestamp corresponding to the latest status update",
    )
    error: str | None = Field(
        default=None,
        description="Last error message encountered during orchestration, if any",
    )

