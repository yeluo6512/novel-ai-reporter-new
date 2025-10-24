"""Helpers for chunking long prompts into provider friendly sizes."""

from __future__ import annotations

from typing import Iterable

from .types import PromptMessage


def chunk_text(content: str, limit: int, overlap: int = 0) -> list[str]:
    """Split *content* into segments whose length does not exceed *limit*.

    The function attempts to split on paragraph, line, or whitespace boundaries to
    preserve readability while allowing a configurable character overlap between
    consecutive chunks.
    """

    cleaned = content.strip()
    if limit <= 0 or not cleaned:
        return [cleaned]
    if len(cleaned) <= limit:
        return [cleaned]

    chunks: list[str] = []
    start = 0
    text_length = len(cleaned)
    while start < text_length:
        end = min(text_length, start + limit)
        split_point = _find_split_point(cleaned, start, end)
        if split_point <= start:
            split_point = min(text_length, start + limit)
        chunk = cleaned[start:split_point].strip()
        if chunk:
            chunks.append(chunk)
        if split_point >= text_length:
            break
        next_start = split_point - overlap if overlap else split_point
        if next_start <= start:
            next_start = split_point
        start = max(0, next_start)

    return chunks or [cleaned]


def build_chunked_conversations(
    messages: Iterable[PromptMessage], limit: int, overlap: int
) -> list[list[PromptMessage]]:
    """Construct chunked conversations preserving system prompts."""

    message_list = list(messages)
    if limit <= 0:
        return [message_list]

    system_messages = [message for message in message_list if message.role == "system"]
    user_messages = [message for message in message_list if message.role == "user"]

    if not user_messages:
        return [message_list]

    combined = "\n\n".join(message.content.strip() for message in user_messages if message.content.strip())
    if not combined:
        return [message_list]

    text_chunks = chunk_text(combined, limit=limit, overlap=overlap)
    conversations: list[list[PromptMessage]] = []
    for chunk in text_chunks:
        chunk_messages = [*system_messages, PromptMessage(role="user", content=chunk)]
        conversations.append(chunk_messages)

    return conversations or [message_list]


def _find_split_point(text: str, start: int, end: int) -> int:
    """Return a natural split point between *start* and *end* indexes."""

    for delimiter in ("\n\n", "\n", " "):
        index = text.rfind(delimiter, start, end)
        if index != -1 and index > start:
            return index + len(delimiter)
    return end


__all__ = ("build_chunked_conversations", "chunk_text")
