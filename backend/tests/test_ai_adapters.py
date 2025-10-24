import pytest

from app.adapters.client import AIClient
from app.adapters.providers import (
    AdapterFactory,
    ClaudeAdapter,
    GeminiAdapter,
    OpenAIAdapter,
)
from app.adapters.system_prompt import SystemPromptManager


def test_openai_adapter_merges_multiple_prompts() -> None:
    adapter = OpenAIAdapter()

    payload = adapter.create_payload(
        model="gpt-4",
        system_prompts=["global guard", "secondary"],
        user_prompts=["first segment", "second segment"],
        temperature=0.2,
    )

    assert payload["model"] == "gpt-4"
    assert payload["messages"] == [
        {"role": "system", "content": "global guard\n\nsecondary"},
        {"role": "user", "content": "first segment\n\nsecond segment"},
    ]
    assert payload["temperature"] == 0.2


def test_gemini_adapter_generates_expected_structure() -> None:
    adapter = GeminiAdapter()

    payload = adapter.create_payload(
        model="gemini-pro",
        system_prompts=["safety", "format"],
        user_prompts=["question", "context"],
    )

    assert payload["model"] == "gemini-pro"
    assert payload["systemInstruction"] == {
        "parts": [{"text": "safety"}, {"text": "format"}]
    }
    assert payload["contents"] == [
        {
            "role": "user",
            "parts": [{"text": "question"}, {"text": "context"}],
        }
    ]


def test_claude_adapter_respects_defaults_and_overrides() -> None:
    adapter = ClaudeAdapter()

    payload = adapter.create_payload(
        model="claude-3-sonnet",
        system_prompts=["core", "safety"],
        user_prompts=["summarise", "details"],
    )

    assert payload["system"] == "core\n\nsafety"
    assert payload["messages"] == [
        {"role": "user", "content": "summarise\n\ndetails"}
    ]
    assert payload["max_tokens"] == 1024

    overridden = adapter.create_payload(
        model="claude-3-sonnet",
        system_prompts="core",
        user_prompts="check",
        max_tokens=256,
    )
    assert overridden["max_tokens"] == 256


def test_system_prompt_manager_priority_and_round_robin() -> None:
    manager = SystemPromptManager(
        [
            ("critical", 2),
            ("fallback", 0),
        ]
    )
    manager.add_prompt("compliance", priority=2)
    manager.add_prompt("style", priority=1)

    first = manager.get_prompts()
    second = manager.get_prompts()
    manager.add_prompt("emergency", priority=3)
    third = manager.get_prompts()

    assert first == ["critical", "compliance", "style", "fallback"]
    assert second == ["compliance", "critical", "style", "fallback"]
    assert third[0] == "emergency"
    assert set(third[1:]) == {"critical", "compliance", "style", "fallback"}


def test_ai_client_integrates_system_prompt_strategy() -> None:
    manager = SystemPromptManager([("base instruction", 0)])
    client = AIClient(provider="openai", model="gpt-4o", system_prompts=manager)

    first_call = client.generate(["hello", "world"])
    assert first_call["messages"][0]["content"] == "base instruction"
    assert first_call["messages"][1]["content"] == "hello\n\nworld"

    client.add_system_prompt("high priority", priority=1)
    second_call = client.generate("follow up")
    assert second_call["messages"][0]["content"].startswith("high priority")
    assert "base instruction" in second_call["messages"][0]["content"]

    third_call = client.generate(
        "another",
        extra_system_prompts="temporary guidance",
    )
    assert third_call["messages"][0]["content"].endswith("temporary guidance")

    fourth_call = client.generate("final")
    assert "temporary guidance" not in fourth_call["messages"][0]["content"]


def test_adapter_factory_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError):
        AdapterFactory.get("unknown")

