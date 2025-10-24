"""API router registration helpers."""

from fastapi import FastAPI

from .routes import health, orchestration

_ROUTERS = (health.router, orchestration.router)


def register_routers(app: FastAPI) -> None:
    """Attach all application routers to the provided FastAPI instance."""

    for router in _ROUTERS:
        app.include_router(router)

__all__ = ("register_routers",)
