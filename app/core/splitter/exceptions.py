"""Custom exceptions raised by the splitter service."""

from __future__ import annotations

from typing import Any


class SplitterError(RuntimeError):
    """Base exception for splitter related failures."""

    def __init__(self, message: str, *, code: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details


class InvalidStrategyError(SplitterError):
    """Raised when an unsupported splitting strategy is requested."""

    def __init__(self, strategy: str) -> None:
        super().__init__(
            f"Unsupported splitting strategy: {strategy}",
            code="splitter.invalid_strategy",
            details={"strategy": strategy},
        )


class StrategyConfigurationError(SplitterError):
    """Raised when strategy parameters fail validation."""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            code="splitter.invalid_configuration",
            details=details,
        )


class ProjectPathError(SplitterError):
    """Raised when a project identifier would resolve to an unsafe filesystem path."""

    def __init__(self, project_id: str) -> None:
        super().__init__(
            "Project identifier contains illegal path characters",
            code="splitter.invalid_project",
            details={"project_id": project_id},
        )


class SplitExecutionError(SplitterError):
    """Raised when split execution fails during file operations."""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            code="splitter.execution_failure",
            details=details,
        )


__all__ = [
    "SplitterError",
    "InvalidStrategyError",
    "StrategyConfigurationError",
    "ProjectPathError",
    "SplitExecutionError",
]
