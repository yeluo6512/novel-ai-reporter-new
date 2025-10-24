from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence

from .providers import AdapterFactory, BaseAdapter, PromptInput
from .system_prompt import SystemPromptManager, PromptDefinition

__all__ = ["AIClient"]


def _flatten_prompts(prompts: PromptInput | None) -> List[str]:
    if prompts is None:
        return []
    if isinstance(prompts, str):
        return [prompts]
    return [str(item) for item in prompts if item is not None]


class AIClient:
    """统一的 AI 调用客户端，封装多家供应商的请求结构。"""

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        system_prompts: Sequence[PromptDefinition] | SystemPromptManager | None = None,
    ) -> None:
        self._adapter: BaseAdapter = AdapterFactory.get(provider)
        self._provider = provider
        self._model = model

        if isinstance(system_prompts, SystemPromptManager):
            self.system_prompt_manager = system_prompts
        else:
            self.system_prompt_manager = SystemPromptManager(system_prompts)

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def model(self) -> str:
        return self._model

    def add_system_prompt(self, prompt: str, priority: int = 0) -> None:
        self.system_prompt_manager.add_prompt(prompt, priority)

    def extend_system_prompts(self, prompts: Iterable[PromptDefinition]) -> None:
        self.system_prompt_manager.extend(prompts)

    def generate(
        self,
        user_prompts: PromptInput | None,
        *,
        extra_system_prompts: PromptInput | None = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        base_prompts = list(self.system_prompt_manager.get_prompts())
        base_prompts.extend(_flatten_prompts(extra_system_prompts))

        return self._adapter.create_payload(
            model=self._model,
            system_prompts=base_prompts,
            user_prompts=user_prompts,
            **kwargs,
        )

