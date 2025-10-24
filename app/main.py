"""Application entrypoint for the FastAPI service."""

from __future__ import annotations

from collections.abc import Sequence

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import register_routers
from .core.agents import AgentsService
from .core.settings import Settings, get_settings

settings: Settings = get_settings()
agents_service = AgentsService(settings=settings)


def create_application() -> FastAPI:
    """Construct and configure the FastAPI application instance."""

    application = FastAPI(title=settings.app_name, version=settings.app_version)
    _configure_cors(application, settings.allowed_origins)

    register_routers(application)
    application.add_event_handler("startup", _on_startup)
    application.add_event_handler("shutdown", _on_shutdown)

    return application


def _configure_cors(app: FastAPI, origins: Sequence[str] | None) -> None:
    allow_all = not origins
    allow_list = ["*"] if allow_all else list(origins or [])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


async def _on_startup() -> None:
    settings.ensure_directories()
    agents_service.initialize()


async def _on_shutdown() -> None:
    agents_service.shutdown()


app = create_application()

__all__ = ("app", "create_application")
