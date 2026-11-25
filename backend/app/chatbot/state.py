"""Typed state for one chatbot generation workflow."""

import uuid
from typing import Any, TypedDict

from langchain_core.messages import BaseMessage
from sqlalchemy.ext.asyncio import AsyncSession


class ChatState(TypedDict, total=False):
    db: AsyncSession
    user_id: uuid.UUID
    conversation_id: uuid.UUID
    user_message_id: uuid.UUID
    message: str
    provider: str
    model: str
    active_provider: str
    active_model: str
    switched_from: str | None
    switch_reason: str | None
    history: list[BaseMessage]
    prompt: Any
    raw_answer: str
    answer: str
    started_at: float
    usage: dict[str, Any]
    assistant_message_id: uuid.UUID
    latency_ms: int
    is_cached: bool
    skip_cache: bool
    cache_lookup: Any
    conversation_language_preference: str | None
    input_language: str
    effective_response_language: str
    language_policy: str
    language_valid: bool
    output_blocked: bool
    output_reason_category: str | None
    proven_context_independent: bool
