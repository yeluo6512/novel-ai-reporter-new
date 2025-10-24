"""System prompt selection utilities."""

from __future__ import annotations

from threading import RLock
from typing import Iterable, Sequence

from .config import PromptSelectionStrategy, SystemPromptConfig


class SystemPromptPool:
    """Stateful selector for configured system prompts."""

    def __init__(self, prompts: Sequence[SystemPromptConfig], strategy: PromptSelectionStrategy) -> None:
        self._lock = RLock()
        self._strategy = strategy
        self._prompts: list[SystemPromptConfig] = [prompt for prompt in prompts if prompt.enabled]
        if self._strategy is PromptSelectionStrategy.PRIORITY:
            self._prompts.sort(key=lambda prompt: prompt.priority, reverse=True)
        self._round_robin_index = 0

    def select_prompts(self) -> list[str]:
        """Return the system prompts to prepend to a request."""

        with self._lock:
            if not self._prompts:
                return []

            if self._strategy is PromptSelectionStrategy.PRIORITY:
                highest_priority = self._prompts[0].priority
                return [prompt.content for prompt in self._prompts if prompt.priority == highest_priority]

            prompt = self._prompts[self._round_robin_index]
            self._round_robin_index = (self._round_robin_index + 1) % len(self._prompts)
            return [prompt.content]

    def update_prompts(self, prompts: Iterable[SystemPromptConfig]) -> None:
        """Replace the underlying prompt set."""

        with self._lock:
            self._prompts = [prompt for prompt in prompts if prompt.enabled]
            if self._strategy is PromptSelectionStrategy.PRIORITY:
                self._prompts.sort(key=lambda prompt: prompt.priority, reverse=True)
            self._round_robin_index = 0

    def reset(self) -> None:
        """Reset internal selection state."""

        with self._lock:
            self._round_robin_index = 0


__all__ = ("SystemPromptPool",)
