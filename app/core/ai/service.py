"""High level AI provider orchestration service."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping
from functools import lru_cache

import httpx

from ..settings import Settings, get_settings
from .chunking import build_chunked_conversations
from .config import ProviderAdapterSettings
from .exceptions import AIProviderError, AIServiceError, ProviderConfigurationError
from .prompts import SystemPromptPool
from .providers.claude import ClaudeClient
from .providers.gemini import GeminiClient
from .providers.openai import OpenAIClient
from .providers.base import ProviderCallRequest, ProviderResponse
from .types import AIRequest, AIResponse, PromptMessage, ProviderName

logger = logging.getLogger(__name__)


class AIService:
    """Facade coordinating prompt orchestration across AI providers."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport_overrides: Mapping[ProviderName, httpx.BaseTransport] | None = None,
    ) -> None:
        self._settings = settings
        self._transport_overrides = dict(transport_overrides or {})
        self._clients = self._initialise_clients()
        self._prompt_pools = self._initialise_prompt_pools()

    async def __aenter__(self) -> "AIService":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - defensive
        await self.aclose()

    async def aclose(self) -> None:
        """Close any underlying HTTP clients."""

        for client in self._clients.values():
            await client.aclose()

    async def generate(self, request: AIRequest) -> AIResponse:
        """Generate a response for the supplied *request*."""

        if not request.messages:
            raise ProviderConfigurationError("AI requests require at least one message")

        config = self._config_for(request.provider)
        if not config.api_key:
            raise ProviderConfigurationError(
                f"API key missing for provider '{request.provider.value}'"
            )

        client = self._clients.get(request.provider)
        if client is None:
            raise ProviderConfigurationError(
                f"Provider '{request.provider.value}' is not supported"
            )

        pool = self._prompt_pools[request.provider]
        base_prompts = pool.select_prompts()
        appended_prompts = list(request.appended_system_prompts or [])

        system_messages = [
            PromptMessage(role="system", content=prompt)
            for prompt in [*base_prompts, *appended_prompts]
        ]
        user_messages = list(request.messages)
        final_messages = [*system_messages, *user_messages]

        conversations = build_chunked_conversations(
            final_messages,
            limit=config.max_chunk_size,
            overlap=min(config.chunk_overlap, max(config.max_chunk_size - 1, 0)),
        )

        chunk_outputs: list[str] = []
        last_model = request.model or config.model or ""
        total_chunks = len(conversations)
        for index, conversation in enumerate(conversations):
            call = ProviderCallRequest(
                messages=list(conversation),
                model=request.model,
                temperature=request.temperature,
                max_output_tokens=request.max_output_tokens,
                metadata={
                    "chunk_index": index,
                    "chunk_count": total_chunks,
                },
            )
            response = await self._invoke_with_retries(
                request.provider, client, call, config, chunk_index=index, chunk_count=total_chunks
            )
            last_model = response.model or last_model
            chunk_outputs.append(response.content)

        combined = "\n\n".join(output for output in chunk_outputs if output)
        metadata = {"chunks": total_chunks}
        return AIResponse(
            provider=request.provider,
            content=combined,
            chunks=chunk_outputs,
            model=last_model,
            metadata=metadata,
        )

    async def _invoke_with_retries(
        self,
        provider: ProviderName,
        client,
        call: ProviderCallRequest,
        config: ProviderAdapterSettings,
        *,
        chunk_index: int,
        chunk_count: int,
    ) -> ProviderResponse:
        max_attempts = config.max_retries + 1
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            start_time = time.perf_counter()
            self._log_event(
                "ai.request.start",
                provider,
                attempt,
                chunk_index,
                chunk_count,
            )
            try:
                response = await client.generate(call)
            except AIProviderError as exc:
                last_error = exc
                duration = time.perf_counter() - start_time
                self._log_event(
                    "ai.request.failure",
                    provider,
                    attempt,
                    chunk_index,
                    chunk_count,
                    duration=duration,
                    error=str(exc),
                )
                if attempt == max_attempts:
                    break
                await asyncio.sleep(self._backoff_delay(attempt))
                continue

            duration = time.perf_counter() - start_time
            self._log_event(
                "ai.request.success",
                provider,
                attempt,
                chunk_index,
                chunk_count,
                duration=duration,
            )
            return response

        if last_error is None:  # pragma: no cover - defensive
            raise AIServiceError(
                f"Unknown failure invoking provider '{provider.value}'"
            )
        raise AIServiceError(
            f"Failed to obtain response from provider '{provider.value}': {last_error}"
        )

    def _initialise_prompt_pools(self) -> dict[ProviderName, SystemPromptPool]:
        settings = self._settings.ai
        return {
            ProviderName.OPENAI: SystemPromptPool(
                settings.openai.system_prompts,
                settings.openai.prompt_selection_strategy,
            ),
            ProviderName.GEMINI: SystemPromptPool(
                settings.gemini.system_prompts,
                settings.gemini.prompt_selection_strategy,
            ),
            ProviderName.CLAUDE: SystemPromptPool(
                settings.claude.system_prompts,
                settings.claude.prompt_selection_strategy,
            ),
        }

    def _initialise_clients(self) -> dict[ProviderName, Any]:
        transports = self._transport_overrides
        return {
            ProviderName.OPENAI: OpenAIClient(
                self._settings.ai.openai,
                transport=transports.get(ProviderName.OPENAI),
            ),
            ProviderName.GEMINI: GeminiClient(
                self._settings.ai.gemini,
                transport=transports.get(ProviderName.GEMINI),
            ),
            ProviderName.CLAUDE: ClaudeClient(
                self._settings.ai.claude,
                transport=transports.get(ProviderName.CLAUDE),
            ),
        }

    def _config_for(self, provider: ProviderName) -> ProviderAdapterSettings:
        match provider:
            case ProviderName.OPENAI:
                return self._settings.ai.openai
            case ProviderName.GEMINI:
                return self._settings.ai.gemini
            case ProviderName.CLAUDE:
                return self._settings.ai.claude
        raise ProviderConfigurationError(f"Unknown provider '{provider}'")

    @staticmethod
    def _backoff_delay(attempt: int) -> float:
        return min(0.2 * (2 ** (attempt - 1)), 2.0)

    @staticmethod
    def _log_event(
        action: str,
        provider: ProviderName,
        attempt: int,
        chunk_index: int,
        chunk_count: int,
        *,
        duration: float | None = None,
        error: str | None = None,
    ) -> None:
        extra = {
            "provider": provider.value,
            "attempt": attempt,
            "chunk_index": chunk_index,
            "chunk_count": chunk_count,
        }
        if duration is not None:
            extra["duration"] = duration
        if error is not None:
            extra["error"] = error
        logger.info(action, extra=extra)


@lru_cache()
def get_ai_service() -> AIService:
    """Return a cached instance of :class:`AIService`."""

    return AIService(get_settings())


__all__ = ("AIService", "get_ai_service")
