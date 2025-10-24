"""OpenAI provider adapter."""

from __future__ import annotations

from typing import Any, Mapping

from ..exceptions import AIProviderError
from .base import BaseAIClient, ProviderCallRequest, ProviderResponse


class OpenAIClient(BaseAIClient):
    """Adapter for OpenAI Chat Completions API."""

    def __init__(self, config, *, transport=None) -> None:
        headers = {"Content-Type": "application/json"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        super().__init__(
            "openai",
            config,
            base_url=config.base_url or "https://api.openai.com/v1",
            default_headers=headers,
            transport=transport,
        )

    def _endpoint(self, call: ProviderCallRequest) -> str:
        return "/chat/completions"

    def _build_payload(self, call: ProviderCallRequest) -> Mapping[str, Any]:
        model = call.model or self.config.model
        if not model:
            raise AIProviderError("OpenAI model is required")

        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in call.messages
            ],
        }
        if call.temperature is not None:
            payload["temperature"] = call.temperature
        if call.max_output_tokens is not None:
            payload["max_tokens"] = call.max_output_tokens
        return payload

    def _parse_response(self, data: Mapping[str, Any], call: ProviderCallRequest) -> ProviderResponse:
        choices = data.get("choices") or []
        if not choices:
            raise AIProviderError("OpenAI response missing choices")
        first_choice = choices[0]
        message = first_choice.get("message") or {}
        content = message.get("content", "")
        model = data.get("model") or call.model or self.config.model or ""
        return ProviderResponse(content=content, model=model, raw=data, metadata={})


__all__ = ("OpenAIClient",)
