"""Common response and error models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field
from pydantic.generics import GenericModel

T = TypeVar("T")


class ErrorDetail(BaseModel):
    """Standardised structure for API error payloads."""

    code: str = Field(..., description="Machine readable error code")
    message: str = Field(..., description="Human readable error message")
    details: dict[str, Any] | None = Field(
        default=None, description="Optional extended error context"
    )


class ResponseEnvelope(GenericModel, Generic[T]):
    """Canonical wrapper around API responses."""

    success: bool = Field(True, description="Indicates if the request was successful")
    data: T | None = Field(
        default=None, description="Payload accompanying a successful response"
    )
    error: ErrorDetail | None = Field(
        default=None, description="Error payload when success is False"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when the response payload was generated",
    )

    @classmethod
    def success_payload(cls, data: T | None = None) -> "ResponseEnvelope[T]":
        """Wrap a successful response payload."""

        return cls(success=True, data=data)

    @classmethod
    def error_payload(
        cls, code: str, message: str, details: dict[str, Any] | None = None
    ) -> "ResponseEnvelope[Any]":
        """Wrap an error response payload."""

        return cls(
            success=False,
            data=None,
            error=ErrorDetail(code=code, message=message, details=details),
        )
