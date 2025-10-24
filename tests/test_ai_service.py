"""Integration style tests for the AI service adapters."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
import pytest

from app.core.ai.config import (
    AIAdapterSettings,
    PromptSelectionStrategy,
    ProviderAdapterSettings,
    SystemPromptConfig,
)
from app.core.ai.exceptions import ProviderConfigurationError
from app.core.ai.service import AIService
from app.core.ai.types import AIRequest, PromptMessage, ProviderName
from app.core.settings import Settings


def _settings_with_openai(**overrides: Any) -> Settings:
    openai_config = ProviderAdapterSettings(
        api_key=overrides.pop("api_key", "test-key"),
        base_url=overrides.pop("base_url", "https://openai.mock"),
        model=overrides.pop("model", "gpt-mock"),
        max_chunk_size=overrides.pop("max_chunk_size", 120),
        chunk_overlap=overrides.pop("chunk_overlap", 10),
        max_retries=overrides.pop("max_retries", 2),
        system_prompts=overrides.pop(
            "system_prompts",
            [
                SystemPromptConfig(name="primary", content="You are a helpful assistant", priority=10),
                SystemPromptConfig(name="secondary", content="Prefer concise answers", priority=5),
            ],
        ),
        prompt_selection_strategy=overrides.pop(
            "prompt_selection_strategy", PromptSelectionStrategy.PRIORITY
        ),
    )
    ai_settings = AIAdapterSettings(openai=openai_config)
    return Settings(ai=ai_settings)


@pytest.mark.asyncio
async def test_chunking_and_reassembly_openai() -> None:
    settings = _settings_with_openai(max_chunk_size=80, chunk_overlap=8)
    captured_payloads: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        captured_payloads.append(payload)
        attempt = len(captured_payloads)
        return httpx.Response(
            status_code=200,
            json={
                "choices": [
                    {
                        "message": {"content": f"chunk-{attempt}"},
                        "finish_reason": "stop",
                    }
                ],
                "model": "gpt-mock",
            },
        )

    transport = httpx.MockTransport(handler)
    large_text = (
        "Section 1 begins with an extended narrative spanning several sentences to ensure "
        "chunking occurs across reasonable boundaries.\n\n"
        "Section 2 continues the thought with additional elaboration that should spill into another chunk."
    )
    request = AIRequest(
        provider=ProviderName.OPENAI,
        messages=[PromptMessage(role="user", content=large_text)],
        appended_system_prompts=("Focus on accuracy.",),
    )

    async with AIService(settings, transport_overrides={ProviderName.OPENAI: transport}) as service:
        response = await service.generate(request)

    assert len(captured_payloads) == 2
    first_payload = captured_payloads[0]
    assert first_payload["messages"][0]["role"] == "system"
    assert first_payload["messages"][0]["content"] == "You are a helpful assistant"
    assert first_payload["messages"][1]["content"] == "Focus on accuracy."
    assert first_payload["messages"][2]["role"] == "user"
    assert "Section 1" in first_payload["messages"][2]["content"]

    second_payload = captured_payloads[1]
    assert second_payload["messages"][2]["role"] == "user"
    assert "Section 2" in second_payload["messages"][2]["content"]
    assert response.content == "chunk-1\n\nchunk-2"
    assert response.chunks == ["chunk-1", "chunk-2"]
    assert response.metadata == {"chunks": 2}


@pytest.mark.asyncio
async def test_round_robin_system_prompts_rotation() -> None:
    system_prompts = [
        SystemPromptConfig(name="alpha", content="Prompt A"),
        SystemPromptConfig(name="beta", content="Prompt B"),
    ]
    settings = _settings_with_openai(
        system_prompts=system_prompts,
        prompt_selection_strategy=PromptSelectionStrategy.ROUND_ROBIN,
        max_chunk_size=500,
    )
    captured_prompts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        captured_prompts.append(payload["messages"][0]["content"])
        return httpx.Response(
            status_code=200,
            json={
                "choices": [{"message": {"content": "ok"}}],
                "model": "gpt-mock",
            },
        )

    transport = httpx.MockTransport(handler)
    request = AIRequest(
        provider=ProviderName.OPENAI,
        messages=[PromptMessage(role="user", content="Evaluate this text.")],
    )

    async with AIService(settings, transport_overrides={ProviderName.OPENAI: transport}) as service:
        await service.generate(request)
        await service.generate(request)
        await service.generate(request)

    assert captured_prompts == ["Prompt A", "Prompt B", "Prompt A"]


@pytest.mark.asyncio
async def test_retry_on_failure_emits_telemetry(caplog: pytest.LogCaptureFixture) -> None:
    settings = _settings_with_openai(max_retries=1)
    attempt_counter = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempt_counter["count"] += 1
        if attempt_counter["count"] == 1:
            return httpx.Response(status_code=500, json={"error": "temporary"})
        return httpx.Response(
            status_code=200,
            json={
                "choices": [{"message": {"content": "recovered"}}],
                "model": "gpt-mock",
            },
        )

    transport = httpx.MockTransport(handler)
    request = AIRequest(
        provider=ProviderName.OPENAI,
        messages=[PromptMessage(role="user", content="Please process this request.")],
    )

    caplog.set_level(logging.INFO)
    async with AIService(settings, transport_overrides={ProviderName.OPENAI: transport}) as service:
        response = await service.generate(request)

    assert response.content == "recovered"
    assert attempt_counter["count"] == 2
    # Ensure both failure and success telemetry entries were emitted
    assert any(record.msg == "ai.request.failure" for record in caplog.records)
    assert any(record.msg == "ai.request.success" for record in caplog.records)


@pytest.mark.asyncio
async def test_missing_api_key_raises_configuration_error() -> None:
    settings = _settings_with_openai(api_key=None)
    request = AIRequest(
        provider=ProviderName.OPENAI,
        messages=[PromptMessage(role="user", content="data")],
    )

    async with AIService(settings) as service:
        with pytest.raises(ProviderConfigurationError):
            await service.generate(request)
