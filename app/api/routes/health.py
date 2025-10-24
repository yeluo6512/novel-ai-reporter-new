"""Health check endpoint."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ...core.settings import get_settings
from ...models.common import ResponseEnvelope

router = APIRouter(tags=["health"])
settings = get_settings()


class HealthStatus(BaseModel):
    """Response model for health check endpoint."""

    status: str = Field(..., description="Overall status indicator")
    service: str = Field(..., description="Name of the service reporting the status")
    version: str = Field(..., description="Application version")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Time at which the health status was generated",
    )


@router.get("/health", response_model=ResponseEnvelope[HealthStatus], summary="Service health status")
async def health_check() -> ResponseEnvelope[HealthStatus]:
    """Return the current health status of the application."""

    payload = HealthStatus(status="ok", service=settings.app_name, version=settings.app_version)
    return ResponseEnvelope.success_payload(payload)
