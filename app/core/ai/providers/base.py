"""Base implementation for provider specific HTTP clients."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping

import httpx

from ..config import ProviderAdapterSettings
from ..exceptions import AIProviderError
from ..types import PromptMessage

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ProviderCallRequest:
    """Internal representation of a provider call."""

    messages: list[PromptMessage]
    model: str | None
    temperature: float | None
    max_output_tokens: int | None
    metadata: Mapping[str, Any]


@dataclass(slots=True)
class ProviderResponse:
    """Wrapper for provider responses after parsing."""

    content: str
    model: str
    raw: Mapping[str, Any]
    metadata: Mapping[str, Any]


class BaseAIClient:
    """Shared HTTP transport and request handling for AI providers."""

    def __init__(
        self,
        name: str,
        config: ProviderAdapterSettings,
        *,
        base_url: str,
        default_headers: dict[str, str] | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._name = name
        self._config = config
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=config.request_timeout,
            headers=default_headers or {},
            transport=transport,
        )

    @property
    def config(self) -> ProviderAdapterSettings:
        return self._config

    async def aclose(self) -> None:
        await self._client.aclose()

    async def generate(self, call: ProviderCallRequest) -> ProviderResponse:
        """Execute the provider request and parse the response."""

        payload = self._build_payload(call)
        request_kwargs = self._request_kwargs(call)

        try:
            response = await self._client.post(self._endpoint(call), json=payload, **request_kwargs)
        except httpx.RequestError as exc:  # pragma: no cover - exercised via retries
            raise AIProviderError(f"{self._name} request transport error") from exc

        if response.status_code >= 400:
            logger.debug(
                "Provider %s responded with error %s: %s",
                self._name,
                response.status_code,
                response.text,
            )
            raise AIProviderError(
                f"{self._name} request failed with status {response.status_code}"
            )

        try:
            parsed = response.json()
        except ValueError as exc:  # pragma: no cover - defensive guard
            raise AIProviderError(f"{self._name} returned invalid JSON") from exc

        return self._parse_response(parsed, call)

    def _request_kwargs(self, call: ProviderCallRequest) -> dict[str, Any]:
        """Additional keyword arguments to forward with the request."""

        return {}

    def _endpoint(self, call: ProviderCallRequest) -> str:
        """Return the endpoint path to POST to."""

        return "/"

    def _build_payload(self, call: ProviderCallRequest) -> Mapping[str, Any]:
        """Serialise the request payload for the provider."""

        raise NotImplementedError

    def _parse_response(self, data: Mapping[str, Any], call: ProviderCallRequest) -> ProviderResponse:
        """Parse the provider specific response payload."""

        raise NotImplementedError


__all__ = (
    "BaseAIClient",
    "ProviderCallRequest",
    "ProviderResponse",
)
