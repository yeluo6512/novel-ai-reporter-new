"""HTTP routes for managing project workspaces and uploads."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import JSONResponse

from ...core.projects import (
    InvalidProjectNameError,
    InvalidProjectUploadError,
    ProjectAlreadyExistsError,
    ProjectNotFoundError,
    ProjectsRepository,
)
from ...core.settings import Settings, get_settings
from ...models.common import ResponseEnvelope
from ...models.project import (
    ProjectCreationResponse,
    ProjectDetail,
    ProjectListResponse,
    ProjectUpdatePayload,
)

router = APIRouter(prefix="/projects", tags=["projects"])


def get_repository(settings: Settings = Depends(get_settings)) -> ProjectsRepository:
    return ProjectsRepository(settings=settings)


def _parse_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    tags = [tag.strip() for tag in raw.split(",")]
    return [tag for tag in tags if tag]


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    envelope = ResponseEnvelope.error_payload(code=code, message=message)
    return JSONResponse(
        status_code=status_code, content=envelope.model_dump(mode="json")
    )


@router.get(
    "",
    response_model=ResponseEnvelope[ProjectListResponse],
    summary="List available projects",
)
async def list_projects(
    repository: ProjectsRepository = Depends(get_repository),
) -> ResponseEnvelope[ProjectListResponse]:
    projects = repository.list_projects()
    payload = ProjectListResponse(items=projects)
    return ResponseEnvelope.success_payload(payload)


@router.post(
    "",
    response_model=ResponseEnvelope[ProjectCreationResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a new project from an uploaded manuscript",
)
async def create_project(
    novel_name: str = Form(..., description="Source novel name for the project"),
    display_name: str | None = Form(
        default=None, description="Optional display name overriding the novel name"
    ),
    description: str | None = Form(
        default=None, description="Optional description for the project"
    ),
    tags: str | None = Form(
        default=None,
        description="Comma separated list of tags applied to the project",
    ),
    upload: UploadFile = File(..., description="Original manuscript .txt upload"),
    repository: ProjectsRepository = Depends(get_repository),
) -> ResponseEnvelope[ProjectCreationResponse] | JSONResponse:
    parsed_tags = _parse_tags(tags)
    try:
        project = await repository.create_project(
            novel_name=novel_name,
            display_name=display_name,
            description=description,
            tags=parsed_tags,
            upload=upload,
        )
    except InvalidProjectNameError as exc:
        return _error_response(
            status.HTTP_400_BAD_REQUEST, "invalid_project_name", str(exc)
        )
    except InvalidProjectUploadError as exc:
        return _error_response(
            status.HTTP_400_BAD_REQUEST, "invalid_project_upload", str(exc)
        )
    except ProjectAlreadyExistsError as exc:
        return _error_response(status.HTTP_409_CONFLICT, "project_exists", str(exc))

    payload = ProjectCreationResponse(project=project)
    return ResponseEnvelope.success_payload(payload)


@router.get(
    "/{identifier}",
    response_model=ResponseEnvelope[ProjectDetail],
    summary="Retrieve a single project",
)
async def get_project(
    identifier: str, repository: ProjectsRepository = Depends(get_repository)
) -> ResponseEnvelope[ProjectDetail] | JSONResponse:
    try:
        project = repository.get_project(identifier)
    except ProjectNotFoundError as exc:
        return _error_response(
            status.HTTP_404_NOT_FOUND, "project_not_found", str(exc)
        )

    return ResponseEnvelope.success_payload(project)


@router.put(
    "/{identifier}",
    response_model=ResponseEnvelope[ProjectDetail],
    summary="Update project metadata",
)
async def update_project(
    identifier: str,
    payload: ProjectUpdatePayload,
    repository: ProjectsRepository = Depends(get_repository),
) -> ResponseEnvelope[ProjectDetail] | JSONResponse:
    try:
        project = repository.update_project(
            identifier,
            name=payload.name,
            description=payload.description,
            tags=payload.tags,
        )
    except ProjectNotFoundError as exc:
        return _error_response(
            status.HTTP_404_NOT_FOUND, "project_not_found", str(exc)
        )
    except InvalidProjectNameError as exc:
        return _error_response(
            status.HTTP_400_BAD_REQUEST, "invalid_project_name", str(exc)
        )

    return ResponseEnvelope.success_payload(project)


@router.delete(
    "/{identifier}",
    response_model=ResponseEnvelope[dict],
    status_code=status.HTTP_200_OK,
    summary="Delete a project and all associated artefacts",
)
async def delete_project(
    identifier: str, repository: ProjectsRepository = Depends(get_repository)
) -> ResponseEnvelope[dict] | JSONResponse:
    try:
        repository.delete_project(identifier)
    except ProjectNotFoundError as exc:
        return _error_response(
            status.HTTP_404_NOT_FOUND, "project_not_found", str(exc)
        )

    return ResponseEnvelope.success_payload({"identifier": identifier})
