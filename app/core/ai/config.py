"""Configuration models for AI provider adapters."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PromptSelectionStrategy(str, Enum):
    """Strategies for selecting configured system prompts."""

    PRIORITY = "priority"
    ROUND_ROBIN = "round_robin"


class SystemPromptConfig(BaseModel):
    """Defines a reusable system prompt for a provider."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(..., description="Identifier for the system prompt")
    content: str = Field(..., description="System prompt content")
    priority: int = Field(0, description="Higher values take precedence for priority selection")
    enabled: bool = Field(True, description="Determines if the prompt can be selected")


class ProviderAdapterSettings(BaseModel):
    """Provider specific adapter configuration."""

    model_config = ConfigDict(validate_assignment=True)

    base_url: str | None = Field(default=None, description="Base URL for the provider API")
    api_key: str | None = Field(default=None, description="API key used for authentication")
    model: str | None = Field(default=None, description="Default model identifier to invoke")
    request_timeout: float = Field(60.0, description="HTTP request timeout in seconds")
    max_chunk_size: int = Field(8000, ge=1, description="Maximum character size per request chunk")
    chunk_overlap: int = Field(200, ge=0, description="Overlap in characters between chunks")
    max_retries: int = Field(2, ge=0, description="Number of retries for transient errors")
    system_prompts: list[SystemPromptConfig] = Field(default_factory=list)
    prompt_selection_strategy: PromptSelectionStrategy = Field(
        default=PromptSelectionStrategy.PRIORITY,
        description="Strategy used when selecting system prompts",
    )
    telemetry_label: str | None = Field(
        default=None,
        description="Optional label used when emitting telemetry logs",
    )

    @field_validator("system_prompts", mode="before")
    @classmethod
    def _coerce_prompts(cls, value: Any) -> Any:
        if not value:
            return []
        if isinstance(value, str):
            # Support comma separated values by generating anonymous prompt entries.
            prompts = [item.strip() for item in value.split(";") if item.strip()]
            return [
                SystemPromptConfig(name=f"prompt_{index}", content=prompt)
                for index, prompt in enumerate(prompts)
            ]
        return value


class AIAdapterSettings(BaseModel):
    """Group of adapter settings for all supported providers."""

    openai: ProviderAdapterSettings = Field(default_factory=ProviderAdapterSettings)
    gemini: ProviderAdapterSettings = Field(default_factory=ProviderAdapterSettings)
    claude: ProviderAdapterSettings = Field(default_factory=ProviderAdapterSettings)


__all__ = (
    "AIAdapterSettings",
    "PromptSelectionStrategy",
    "ProviderAdapterSettings",
    "SystemPromptConfig",
)
