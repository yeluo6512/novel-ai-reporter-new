"""Project level metadata models and API schemas."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class ProjectMetadata(BaseModel):
    """Summary metadata describing a managed project workspace."""

    model_config = ConfigDict(extra="ignore")

    identifier: str = Field(..., description="Unique identifier for the project")
    name: str = Field(..., description="Human readable project name")
    description: str | None = Field(
        default=None, description="Optional project description"
    )
    tags: list[str] = Field(
        default_factory=list, description="Optional set of tags for the project"
    )
    workspace_path: Path | None = Field(
        default=None, description="Filesystem path associated with the project"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp marking when the project was created",
    )
    updated_at: datetime | None = Field(
        default=None, description="Timestamp of last update to the project"
    )


class ProjectFileInfo(BaseModel):
    """Metadata about the original uploaded manuscript file."""

    filename: str = Field(..., description="Original filename supplied by the client")
    content_type: str | None = Field(
        default=None, description="Reported MIME type for the uploaded file"
    )
    size: int = Field(..., ge=0, description="Size of the uploaded file in bytes")
    chunks: int = Field(
        default=0,
        ge=0,
        description="Number of streamed chunks written to disk during upload",
    )
    uploaded_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp at which the upload completed",
    )
    relative_path: str = Field(
        ..., description="Relative path to the stored file within the project workspace"
    )


class ProjectArtifact(BaseModel):
    """Descriptor for derived artefacts generated for a project."""

    name: str = Field(..., description="Filename of the artefact")
    relative_path: str = Field(
        ..., description="Relative path to the artefact within the project workspace"
    )
    size: int = Field(..., ge=0, description="Size of the artefact in bytes")
    modified_at: datetime = Field(
        ..., description="Last modified timestamp sourced from the filesystem"
    )


class ProjectDetail(ProjectMetadata):
    """Full project representation including file and artefact metadata."""

    original_file: ProjectFileInfo | None = Field(
        default=None, description="Metadata for the original manuscript upload"
    )
    artifacts: list[ProjectArtifact] = Field(
        default_factory=list,
        description="Collection of artefacts derived from the project",
    )


class ProjectListResponse(BaseModel):
    """Container for listing multiple projects."""

    items: list[ProjectDetail] = Field(
        default_factory=list, description="Ordered collection of project records"
    )


class ProjectCreationResponse(BaseModel):
    """Payload returned when a project is created from an upload."""

    project: ProjectDetail = Field(..., description="Created project descriptor")


class ProjectUpdatePayload(BaseModel):
    """Payload accepted when updating project metadata."""

    name: str | None = Field(
        default=None, description="Updated human readable project name"
    )
    description: str | None = Field(
        default=None, description="Updated project description"
    )
    tags: list[str] | None = Field(
        default=None, description="Replacement list of tags for the project"
    )
