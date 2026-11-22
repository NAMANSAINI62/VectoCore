"""SQLAlchemy model for persistent multilingual semantic cache storage."""

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class CacheEntry(Base):
    """Stores completed query-response pairs with embeddings, intent, and extracted entities."""

    __tablename__ = "cache_entries"
    __table_args__ = (
        Index("ix_cache_entries_owner_status", "owner_id", "status"),
        Index("ix_cache_entries_config_hash", "config_hash"),
        Index("ix_cache_entries_intent", "intent"),
        Index("ix_cache_entries_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_query: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Native pgvector(2048) on PostgreSQL with JSON fallback for SQLite unit tests
    query_embedding: Mapped[list[float]] = mapped_column(
        Vector(2048).with_variant(JSON(), "sqlite"),
        nullable=False,
    )
    embedding_dim: Mapped[int] = mapped_column(Integer, nullable=False, default=2048)
    embedding_model: Mapped[str] = mapped_column(String(120), nullable=False)

    response: Mapped[str] = mapped_column(Text, nullable=False)
    detected_language: Mapped[str] = mapped_column(String(80), nullable=False, default="English")
    
    # Intent and Entity Validation Guard Fields
    intent: Mapped[str] = mapped_column(String(40), nullable=False, default="definition")
    depth_scope: Mapped[str] = mapped_column(String(20), nullable=False, default="standard")
    critical_entities: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False, default="pre-guardrails")

    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_hit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CacheTelemetry(Base):
    """Real telemetry tracking every request, cache outcome, token counts, and latency."""

    __tablename__ = "cache_telemetry"
    __table_args__ = (
        Index("ix_cache_telemetry_owner_created", "owner_id", "created_at"),
        Index("ix_cache_telemetry_status", "cache_status"),
        CheckConstraint(
            "cache_status IN ('exact_hit', 'semantic_hit', 'miss', 'bypass', 'error', 'blocked')",
            name="ck_cache_telemetry_cache_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_conversations.id", ondelete="SET NULL"), nullable=True
    )

    query_preview: Mapped[str] = mapped_column(String(255), nullable=False)
    detected_language: Mapped[str] = mapped_column(String(80), nullable=False, default="English")
    requested_language: Mapped[str] = mapped_column(String(80), nullable=False, default="English")
    cache_status: Mapped[str] = mapped_column(String(20), nullable=False)  # 'exact_hit', 'semantic_hit', 'miss', 'bypass', 'error', 'blocked'
    similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    matched_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    matched_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_candidates: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    current_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched_queries_snapshot: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    rejected_candidates_snapshot: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    returned_response_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    variant_reused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    translation_performed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    translation_failed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    translation_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)

    # 100% Real Tokens
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_saved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Latency Breakdown (ms)
    total_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_lookup_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    llm_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_saved_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embedding_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pgvector_search_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    compatibility_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CacheSettings(Base):
    """Per-user persistent semantic cache threshold and TTL configuration."""

    __tablename__ = "cache_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    similarity_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.82)
    default_ttl_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=72)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
