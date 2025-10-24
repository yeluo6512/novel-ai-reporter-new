from __future__ import annotations

from collections import defaultdict, deque
from typing import Deque, Dict, Iterable, List, Sequence, Tuple

__all__ = ["SystemPromptManager"]

PromptDefinition = Tuple[str, int]


class SystemPromptManager:
    """管理系统提示词的优先级和轮询调度。"""

    def __init__(self, prompts: Sequence[PromptDefinition] | None = None) -> None:
        self._queues: Dict[int, Deque[str]] = defaultdict(deque)
        if prompts:
            self.extend(prompts)

    def add_prompt(self, prompt: str, priority: int = 0) -> None:
        self._queues[int(priority)].append(prompt)

    def extend(self, prompts: Iterable[PromptDefinition]) -> None:
        for prompt, priority in prompts:
            self.add_prompt(prompt, priority)

    def clear(self) -> None:
        self._queues.clear()

    def get_prompts(self) -> List[str]:
        """按照优先级返回系统提示词，并在相同优先级内轮询。"""

        result: List[str] = []
        for priority in sorted(self._queues.keys(), reverse=True):
            queue = self._queues[priority]
            if not queue:
                continue

            result.extend(list(queue))
            if len(queue) > 1:
                queue.rotate(-1)

        return result

    def snapshot(self) -> List[PromptDefinition]:
        """返回当前提示词及其优先级，不影响轮询顺序。"""

        snapshot: List[PromptDefinition] = []
        for priority in sorted(self._queues.keys(), reverse=True):
            queue = self._queues[priority]
            snapshot.extend((prompt, priority) for prompt in queue)
        return snapshot

    def __len__(self) -> int:  # pragma: no cover - 简单属性
        return sum(len(queue) for queue in self._queues.values())

