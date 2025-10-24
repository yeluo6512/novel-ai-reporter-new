"""Models describing persisted application-level settings."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


class ProviderConfiguration(BaseModel):
    """Configuration persisted for upstream provider access."""

    model_config = ConfigDict(extra="allow")

    base_url: str | None = Field(
        default=None, description="Base URL for the selected provider service"
    )
    api_key: str | None = Field(
        default=None, description="API key used to authenticate with the provider"
    )


class PromptPreferences(BaseModel):
    """User-adjustable preferences controlling prompt construction."""

    model_config = ConfigDict(extra="allow")

    default_prompt: str | None = Field(
        default=None, description="Default system prompt applied to new sessions"
    )
    temperature: float | None = Field(
        default=None,
        description="Preferred creativity/temperature value for completions",
    )


class ApplicationSettingsPayload(BaseModel):
    """Payload persisted for application-level settings."""

    provider: ProviderConfiguration = Field(
        default_factory=ProviderConfiguration,
        description="Persisted provider configuration overrides",
    )
    prompts: PromptPreferences = Field(
        default_factory=PromptPreferences,
        description="Persisted prompt preference overrides",
    )


class AgentsReloadResponse(BaseModel):
    """Response payload returned when agents metadata is reloaded."""

    reloaded: bool = Field(..., description="Indicator that the reload was executed")
    version: str = Field(..., description="Resolved version from the manifest")
    cached_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when the manifest was (re)cached",
    )
    generated_at: datetime | None = Field(
        default=None,
        description="Timestamp from inside the manifest when present",
    )
    manifest_path: str = Field(
        ..., description="Filesystem path to the manifest that was reloaded"
    )
