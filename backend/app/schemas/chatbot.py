"""Contracts for the authenticated general-purpose chatbot API."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.config.settings import get_settings

_settings = get_settings()


class ConversationCreate(BaseModel):
    title: str = Field(default="New chat", min_length=1, max_length=180)
    provider: str = Field(default=_settings.CHAT_DEFAULT_PROVIDER, min_length=2, max_length=40)
    model: str = Field(default=_settings.GROQ_DEFAULT_MODEL, min_length=2, max_length=160)


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    provider: str | None = Field(default=None, min_length=2, max_length=40)
    model: str | None = Field(default=None, min_length=2, max_length=160)


class ChatCompletionRequest(BaseModel):
    conversation_id: uuid.UUID | None = None
    message: str = Field(min_length=1, max_length=25000)
    provider: str = Field(default=_settings.CHAT_DEFAULT_PROVIDER, min_length=2, max_length=40)
    model: str = Field(default=_settings.GROQ_DEFAULT_MODEL, min_length=2, max_length=160)

    @field_validator("message")
    @classmethod
    def message_must_contain_non_whitespace(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message cannot be empty.")
        return value


class ChatMessageResponse(BaseModel):
    id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str
    provider: str | None = None
    model_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationResponse(BaseModel):
    id: uuid.UUID
    title: str
    selected_provider: str
    selected_model: str
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessageResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ProviderResponse(BaseModel):
    id: str
    configured: bool
    models: list[str]


class ModelResponse(BaseModel):
    id: str
    name: str
    provider: str
    tier: str | None = None


class TextToSpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=25000)

    @field_validator("text")
    @classmethod
    def text_must_contain_non_whitespace(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Text cannot be empty.")
        return value


class AudioTranscribeResponse(BaseModel):
    transcript: str
    model: str


class VoicePolishRequest(BaseModel):
    text: str = Field(min_length=1, max_length=25000)

    @field_validator("text")
    @classmethod
    def voice_text_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Text cannot be empty.")
        return value


class VoicePolishResponse(BaseModel):
    polished_text: str
    raw_text: str
