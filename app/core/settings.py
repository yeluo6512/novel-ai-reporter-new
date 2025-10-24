"""Application settings and configuration management."""

from __future__ import annotations

import os
from functools import cached_property, lru_cache
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_base_dir() -> Path:
    """Determine a sensible default base directory for the application."""

    base_dir_env = os.getenv("APP_BASE_DIR") or os.getenv("BASE_DIR")
    if base_dir_env:
        return Path(base_dir_env).expanduser()

    docker_default = Path("/app")
    if docker_default.exists() or os.access(docker_default.parent, os.W_OK):
        return docker_default

    return Path(__file__).resolve().parents[2]


class AppPaths(BaseModel):
    """Resolved filesystem paths used by the application."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    base_dir: Path
    config_dir: Path
    data_dir: Path
    projects_dir: Path


class Settings(BaseSettings):
    """Runtime configuration derived from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=(".env",),
        extra="ignore",
    )

    app_name: str = Field(default="CTO Agents Backend")
    app_version: str = Field(default="0.1.0")
    environment: str = Field(default="development")

    provider_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("APP_PROVIDER_API_KEY", "PROVIDER_API_KEY"),
        description="Credential used to authenticate with external providers.",
    )
    provider_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("APP_PROVIDER_BASE_URL", "PROVIDER_BASE_URL"),
        description="Base URL for interacting with external provider APIs.",
    )

    allowed_origins: list[str] = Field(
        default_factory=list,
        description="List of origins permitted by CORS configuration.",
    )

    base_dir: Path = Field(
        default_factory=_default_base_dir,
        validation_alias=AliasChoices("APP_BASE_DIR", "BASE_DIR"),
        description="Root directory for application data and configuration.",
    )
    data_dir: Path | None = Field(
        default=None,
        validation_alias=AliasChoices("APP_DATA_DIR", "DATA_DIR"),
        description="Optional override for data directory location.",
    )
    config_dir: Path | None = Field(
        default=None,
        validation_alias=AliasChoices("APP_CONFIG_DIR", "CONFIG_DIR"),
        description="Optional override for configuration directory location.",
    )

    projects_subdir: str = Field(
        default="projects",
        description="Name of the projects sub-directory within the data directory.",
    )
    agents_manifest_name: str = Field(
        default="agents.md",
        description="Filename for the agents manifest within the config directory.",
    )

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_allowed_origins(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @cached_property
    def paths(self) -> AppPaths:
        base_dir = self.base_dir.expanduser().resolve()
        data_source = self.data_dir or (base_dir / "data")
        data_dir = Path(data_source).expanduser().resolve()
        config_source = self.config_dir or (base_dir / "config")
        config_dir = Path(config_source).expanduser().resolve()
        projects_dir = (data_dir / self.projects_subdir).resolve()
        return AppPaths(
            base_dir=base_dir,
            config_dir=config_dir,
            data_dir=data_dir,
            projects_dir=projects_dir,
        )

    @cached_property
    def agents_manifest_path(self) -> Path:
        return (self.paths.config_dir / self.agents_manifest_name).resolve()

    def ensure_directories(self) -> None:
        """Create required data directories if they do not already exist."""

        for path in {
            self.paths.base_dir,
            self.paths.config_dir,
            self.paths.data_dir,
            self.paths.projects_dir,
        }:
            path.mkdir(parents=True, exist_ok=True)


@lru_cache()
def get_settings() -> Settings:
    """Return a cached instance of application settings."""

    return Settings()
