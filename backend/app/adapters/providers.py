from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Dict, Iterable, List, Sequence, Union

PromptInput = Union[str, Sequence[str]]

__all__ = [
    "PromptInput",
    "BaseAdapter",
    "OpenAIAdapter",
    "GeminiAdapter",
    "ClaudeAdapter",
    "AdapterFactory",
]


def _normalize_prompt_input(prompts: PromptInput | None = None) -> List[str]:
    if prompts is None:
        return []

    if isinstance(prompts, str):
        return [prompts]

    normalized: List[str] = []
    for item in prompts:
        if item is None:
            continue
        text = str(item)
        if text:
            normalized.append(text)
    return normalized


def _merge_segments(segments: Iterable[str]) -> str:
    return "\n\n".join(segment for segment in segments if segment)


class BaseAdapter(ABC):
    provider_name: ClassVar[str]

    @abstractmethod
    def create_payload(
        self,
        *,
        model: str,
        system_prompts: PromptInput | None = None,
        user_prompts: PromptInput | None = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """构建特定供应商的请求负载。"""

    def _normalize(self, prompts: PromptInput | None) -> List[str]:
        return _normalize_prompt_input(prompts)

    def _join(self, prompts: PromptInput | None) -> str:
        return _merge_segments(self._normalize(prompts))


class OpenAIAdapter(BaseAdapter):
    provider_name = "openai"

    def create_payload(
        self,
        *,
        model: str,
        system_prompts: PromptInput | None = None,
        user_prompts: PromptInput | None = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        system_text = self._join(system_prompts)
        system_messages = (
            [{"role": "system", "content": system_text}]
            if system_text
            else []
        )

        user_text = self._join(user_prompts)
        user_message = (
            [{"role": "user", "content": user_text}]
            if user_text
            else []
        )

        payload: Dict[str, Any] = {
            "model": model,
            "messages": system_messages + user_message,
        }
        payload.update(kwargs)
        return payload


class GeminiAdapter(BaseAdapter):
    provider_name = "gemini"

    def create_payload(
        self,
        *,
        model: str,
        system_prompts: PromptInput | None = None,
        user_prompts: PromptInput | None = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        system_parts = [
            {"text": prompt} for prompt in self._normalize(system_prompts)
        ]

        content_parts = [
            {"text": prompt} for prompt in self._normalize(user_prompts)
        ]

        payload: Dict[str, Any] = {
            "model": model,
            "contents": (
                [{"role": "user", "parts": content_parts}] if content_parts else []
            ),
        }

        if system_parts:
            payload["systemInstruction"] = {"parts": system_parts}

        payload.update(kwargs)
        return payload


class ClaudeAdapter(BaseAdapter):
    provider_name = "claude"

    def create_payload(
        self,
        *,
        model: str,
        system_prompts: PromptInput | None = None,
        user_prompts: PromptInput | None = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        system_text = self._join(system_prompts)
        user_text = self._join(user_prompts)

        payload: Dict[str, Any] = {"model": model}

        if system_text:
            payload["system"] = system_text

        if user_text:
            payload["messages"] = [{"role": "user", "content": user_text}]
        else:
            payload["messages"] = []

        payload.update(kwargs)
        payload.setdefault("max_tokens", 1024)
        return payload


class AdapterFactory:
    _registry: Dict[str, BaseAdapter] = {
        OpenAIAdapter.provider_name: OpenAIAdapter(),
        GeminiAdapter.provider_name: GeminiAdapter(),
        ClaudeAdapter.provider_name: ClaudeAdapter(),
    }

    @classmethod
    def get(cls, provider: str) -> BaseAdapter:
        try:
            return cls._registry[provider.lower()]
        except KeyError as exc:
            raise ValueError(f"Unsupported AI provider: {provider}") from exc

