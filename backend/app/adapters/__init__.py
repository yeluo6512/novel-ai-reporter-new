"""统一的 AI 适配器接口实现。"""

from .client import AIClient
from .providers import AdapterFactory, ClaudeAdapter, GeminiAdapter, OpenAIAdapter
from .system_prompt import SystemPromptManager

__all__ = [
    "AIClient",
    "AdapterFactory",
    "ClaudeAdapter",
    "GeminiAdapter",
    "OpenAIAdapter",
    "SystemPromptManager",
]
