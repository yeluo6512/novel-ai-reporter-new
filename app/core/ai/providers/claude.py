"""Claude provider adapter."""

from __future__ import annotations

from typing import Any, Mapping

from ..exceptions import AIProviderError
from .base import BaseAIClient, ProviderCallRequest, ProviderResponse


class ClaudeClient(BaseAIClient):
    """Adapter for Anthropic Claude Messages API."""

    def __init__(self, config, *, transport=None) -> None:
        headers = {
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        if config.api_key:
            headers["x-api-key"] = config.api_key
        super().__init__(
            "claude",
            config,
            base_url=config.base_url or "https://api.anthropic.com",
            default_headers=headers,
            transport=transport,
        )

    def _endpoint(self, call: ProviderCallRequest) -> str:
        return "/v1/messages"

    def _build_payload(self, call: ProviderCallRequest) -> Mapping[str, Any]:
        model = call.model or self.config.model
        if not model:
            raise AIProviderError("Claude model is required")

        system_prompts = [message.content for message in call.messages if message.role == "system"]
        conversation = [
            {"role": message.role, "content": message.content}
            for message in call.messages
            if message.role != "system"
        ]
        if not conversation:
            raise AIProviderError("Claude requests require at least one conversation message")

        payload: dict[str, Any] = {
            "model": model,
            "messages": conversation,
        }
        if system_prompts:
            payload["system"] = "\n\n".join(system_prompts)
        if call.max_output_tokens is not None:
            payload["max_tokens"] = call.max_output_tokens
        if call.temperature is not None:
            payload["temperature"] = call.temperature
        return payload

    def _parse_response(self, data: Mapping[str, Any], call: ProviderCallRequest) -> ProviderResponse:
        content_items = data.get("content") or []
        if not isinstance(content_items, list):
            raise AIProviderError("Claude response missing content list")
        compiled = "".join(
            item.get("text", "") if isinstance(item, dict) else ""
            for item in content_items
        )
        if not compiled and isinstance(data.get("output_text"), str):
            compiled = data["output_text"]
        model = data.get("model") or call.model or self.config.model or ""
        return ProviderResponse(content=compiled, model=model, raw=data, metadata={})


__all__ = ("ClaudeClient",)
