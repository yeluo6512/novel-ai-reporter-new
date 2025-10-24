"""Project level metadata models."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List

from pydantic import BaseModel, ConfigDict, Field


class ProjectMetadata(BaseModel):
    """Summary metadata describing a managed project workspace."""

    model_config = ConfigDict(extra="ignore")

    identifier: str = Field(..., description="Unique identifier for the project")
    name: str = Field(..., description="Human readable project name")
    description: str | None = Field(
        default=None, description="Optional project description"
    )
    tags: List[str] = Field(
        default_factory=list, description="Optional set of tags for the project"
    )
    workspace_path: Path | None = Field(
        default=None, description="Filesystem path associated with the project"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp marking when the project was created",
    )
    updated_at: datetime | None = Field(
        default=None, description="Timestamp of last update to the project"
    )
