"""HTTP routes for persisted runtime settings and agent controls."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from ...core.agents import get_agents_service
from ...core.preferences import ApplicationSettingsStore
from ...core.settings import Settings, get_settings
from ...models.common import ResponseEnvelope
from ...models.settings import AgentsReloadResponse, ApplicationSettingsPayload

router = APIRouter(prefix="/settings", tags=["settings"])


def get_store(settings: Settings = Depends(get_settings)) -> ApplicationSettingsStore:
    return ApplicationSettingsStore(settings=settings)


@router.get(
    "",
    response_model=ResponseEnvelope[ApplicationSettingsPayload],
    summary="Retrieve persisted application settings",
)
async def read_settings(
    store: ApplicationSettingsStore = Depends(get_store),
) -> ResponseEnvelope[ApplicationSettingsPayload]:
    payload = store.read()
    return ResponseEnvelope.success_payload(payload)


@router.put(
    "",
    response_model=ResponseEnvelope[ApplicationSettingsPayload],
    summary="Persist application settings overrides",
)
async def update_settings(
    payload: ApplicationSettingsPayload,
    store: ApplicationSettingsStore = Depends(get_store),
) -> ResponseEnvelope[ApplicationSettingsPayload]:
    updated = store.write(payload)
    return ResponseEnvelope.success_payload(updated)


@router.post(
    "/agents/reload",
    response_model=ResponseEnvelope[AgentsReloadResponse],
    status_code=status.HTTP_200_OK,
    summary="Reload the agents manifest and return metadata",
)
async def reload_agents() -> ResponseEnvelope[AgentsReloadResponse]:
    service = get_agents_service()
    manifest = service.prepare_for_task()
    metadata = manifest.metadata
    payload = AgentsReloadResponse(
        reloaded=True,
        version=metadata.version,
        cached_at=metadata.cached_at,
        generated_at=metadata.generated_at,
        manifest_path=str(metadata.file_path),
    )
    return ResponseEnvelope.success_payload(payload)
