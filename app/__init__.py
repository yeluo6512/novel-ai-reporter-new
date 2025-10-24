"""Application package exposing the FastAPI app instance."""

from .main import app, create_application

__all__ = ("app", "create_application")
