"""Common types for AI provider adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, Sequence


class ProviderName(str, Enum):
    """Supported AI provider identifiers."""

    OPENAI = "openai"
    GEMINI = "gemini"
    CLAUDE = "claude"


MessageRole = Literal["system", "user", "assistant"]


@dataclass(slots=True)
class PromptMessage:
    """A single message in a prompt exchange."""

    role: MessageRole
    content: str


@dataclass(slots=True)
class AIRequest:
    """High level request descriptor for the AI service."""

    provider: ProviderName
    messages: Sequence[PromptMessage]
    model: str | None = None
    temperature: float | None = None
    appended_system_prompts: Sequence[str] = field(default_factory=tuple)
    max_output_tokens: int | None = None


@dataclass(slots=True)
class AIResponse:
    """Structured response returned by the AI service."""

    provider: ProviderName
    content: str
    chunks: list[str]
    model: str
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = (
    "AIRequest",
    "AIResponse",
    "MessageRole",
    "PromptMessage",
    "ProviderName",
)
