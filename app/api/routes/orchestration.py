"""API endpoints for orchestration workflows and report management."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, status
from pydantic import BaseModel, Field, field_validator

from ...models.common import ResponseEnvelope
from ...models.orchestration import OrchestrationStatus
from ...services.orchestration import (
    OrchestrationError,
    OrchestrationService,
    ProjectWorkspaceError,
    TaskConflictError,
)

router = APIRouter(prefix="/projects", tags=["orchestration"])

orchestration_service = OrchestrationService()


class GenerationRequest(BaseModel):
    """Request payload for triggering orchestration generation."""

    regenerate_segments: list[int] | None = Field(
        default=None,
        description="Optional list of segment indices to regenerate",
    )
    cascade: bool = Field(
        default=True,
        description="Whether to recompute downstream integrations after regeneration",
    )

    @field_validator("regenerate_segments")
    @classmethod
    def _ensure_non_negative(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return value
        if not value:
            return []
        deduplicated = sorted(set(value))
        if any(index < 0 for index in deduplicated):
            raise ValueError("Segment indices must be non-negative")
        return deduplicated


class FinalReportUpdate(BaseModel):
    """Payload for persisting manual edits to the final report."""

    content: str = Field(..., description="Markdown content for the final report")


class FinalReportResponse(BaseModel):
    """Response payload wrapper when returning final report content."""

    project_id: str = Field(..., description="Identifier for the project workspace")
    content: str = Field(..., description="Markdown content of the final report")


@router.post(
    "/{project_id}/reports/generate",
    response_model=ResponseEnvelope[OrchestrationStatus],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger orchestration workflow",
)
async def trigger_generation(
    project_id: str,
    request: GenerationRequest,
    background_tasks: BackgroundTasks,
) -> ResponseEnvelope[OrchestrationStatus]:
    """Start the analysis, integration, and final report pipeline in the background."""

    try:
        status_model = orchestration_service.start_background_task(
            project_id=project_id,
            background_tasks=background_tasks,
            regenerate_segments=request.regenerate_segments,
            cascade=request.cascade,
        )
    except TaskConflictError as exc:
        return ResponseEnvelope.error_payload("task_conflict", str(exc))
    except ProjectWorkspaceError as exc:
        return ResponseEnvelope.error_payload("workspace_not_ready", str(exc))
    except OrchestrationError as exc:
        return ResponseEnvelope.error_payload("orchestration_error", str(exc))

    return ResponseEnvelope.success_payload(status_model)


@router.get(
    "/{project_id}/reports/status",
    response_model=ResponseEnvelope[OrchestrationStatus],
    summary="Retrieve orchestration status",
)
async def get_status(project_id: str) -> ResponseEnvelope[OrchestrationStatus]:
    """Return the current orchestration status for a project."""

    status_model = orchestration_service.get_status(project_id)
    return ResponseEnvelope.success_payload(status_model)


@router.get(
    "/{project_id}/reports/final",
    response_model=ResponseEnvelope[FinalReportResponse],
    summary="Fetch final report content",
)
async def read_final_report(project_id: str) -> ResponseEnvelope[FinalReportResponse]:
    """Retrieve the generated final report content for a project."""

    try:
        content = orchestration_service.read_final_report(project_id)
    except ProjectWorkspaceError as exc:
        return ResponseEnvelope.error_payload("workspace_not_ready", str(exc))
    except OrchestrationError as exc:
        return ResponseEnvelope.error_payload("orchestration_error", str(exc))
    except FileNotFoundError:
        return ResponseEnvelope.error_payload(
            "final_report_missing",
            "Final report has not been generated yet for this project.",
        )

    payload = FinalReportResponse(project_id=project_id, content=content)
    return ResponseEnvelope.success_payload(payload)


@router.put(
    "/{project_id}/reports/final",
    response_model=ResponseEnvelope[OrchestrationStatus],
    summary="Persist manual final report edits",
)
async def update_final_report(
    project_id: str,
    payload: FinalReportUpdate,
) -> ResponseEnvelope[OrchestrationStatus]:
    """Save manual edits to the project's final report."""

    try:
        status_model = orchestration_service.save_final_report(project_id, payload.content)
    except ProjectWorkspaceError as exc:
        return ResponseEnvelope.error_payload("workspace_not_ready", str(exc))
    except OrchestrationError as exc:
        return ResponseEnvelope.error_payload("orchestration_error", str(exc))

    return ResponseEnvelope.success_payload(status_model)
