"""Gemini provider adapter."""

from __future__ import annotations

from typing import Any, Mapping

from ..exceptions import AIProviderError
from .base import BaseAIClient, ProviderCallRequest, ProviderResponse


class GeminiClient(BaseAIClient):
    """Adapter for Google Gemini generateContent API."""

    def __init__(self, config, *, transport=None) -> None:
        headers = {"Content-Type": "application/json"}
        if config.api_key:
            headers["x-goog-api-key"] = config.api_key
        super().__init__(
            "gemini",
            config,
            base_url=config.base_url or "https://generativelanguage.googleapis.com",
            default_headers=headers,
            transport=transport,
        )

    def _endpoint(self, call: ProviderCallRequest) -> str:
        model = call.model or self.config.model
        if not model:
            raise AIProviderError("Gemini model is required")
        return f"/v1beta/models/{model}:generateContent"

    def _build_payload(self, call: ProviderCallRequest) -> Mapping[str, Any]:
        user_contents = [
            {
                "role": message.role,
                "parts": [{"text": message.content}],
            }
            for message in call.messages
            if message.role != "system"
        ]
        if not user_contents:
            raise AIProviderError("Gemini requests require at least one user message")

        payload: dict[str, Any] = {"contents": user_contents}
        system_prompts = [message.content for message in call.messages if message.role == "system"]
        if system_prompts:
            payload["systemInstruction"] = {
                "parts": [{"text": "\n\n".join(system_prompts)}]
            }

        generation_config: dict[str, Any] = {}
        if call.temperature is not None:
            generation_config["temperature"] = call.temperature
        if call.max_output_tokens is not None:
            generation_config["maxOutputTokens"] = call.max_output_tokens
        if generation_config:
            payload["generationConfig"] = generation_config

        return payload

    def _parse_response(self, data: Mapping[str, Any], call: ProviderCallRequest) -> ProviderResponse:
        candidates = data.get("candidates") or []
        if not candidates:
            raise AIProviderError("Gemini response missing candidates")
        first_candidate = candidates[0]
        parts = (first_candidate.get("content") or {}).get("parts") or []
        content = "".join(part.get("text", "") for part in parts)
        model = call.model or self.config.model or first_candidate.get("model", "")
        return ProviderResponse(content=content, model=model, raw=data, metadata={})


__all__ = ("GeminiClient",)
