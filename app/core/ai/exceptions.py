"""Custom exceptions for AI provider orchestration."""

from __future__ import annotations


class AIServiceError(RuntimeError):
    """Base exception for AI service failures."""


class ProviderConfigurationError(AIServiceError):
    """Raised when a provider is not correctly configured for use."""


class AIProviderError(AIServiceError):
    """Raised when a provider adapter encounters a request/response issue."""


__all__ = (
    "AIProviderError",
    "AIServiceError",
    "ProviderConfigurationError",
)
