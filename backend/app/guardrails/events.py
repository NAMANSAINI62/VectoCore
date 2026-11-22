"""Structured JSON security logging, keyed HMAC hashing, and PostgreSQL guardrail_events persistence.

Raw user or assistant text is never accepted, logged, or persisted by this module.
"""

import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import CheckConstraint, DateTime, Float, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.guardrails.schemas import Decision, ScoreBand, SecurityEvent

logger = logging.getLogger("guardrails.security_events")

_ALLOWED_EVENT_KEYS = frozenset({
    "id",
    "request_id",
    "user_id_hash",
    "layer",
    "decision",
    "score_band",
    "detector",
    "latency_ms",
    "policy_version",
    "mode",
    "message_hash",
    "message_length",
    "created_at",
})


class GuardrailEvent(Base):
    """SQLAlchemy ORM model for `guardrail_events`. Contains zero raw-text columns."""

    __tablename__ = "guardrail_events"
    __table_args__ = (
        Index("ix_guardrail_events_request_id", "request_id"),
        Index("ix_guardrail_events_user_created", "user_id_hash", "created_at"),
        Index("ix_guardrail_events_layer_decision", "layer", "decision"),
        CheckConstraint(
            "mode IN ('shadow', 'enforce')",
            name="ck_guardrail_events_mode",
        ),
        CheckConstraint(
            "decision IN ('ALLOW', 'BLOCK', 'REDACT', 'REQUIRE_REVIEW', 'FALLBACK')",
            name="ck_guardrail_events_decision",
        ),
        CheckConstraint(
            "message_length >= 0",
            name="ck_guardrail_events_message_length",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    layer: Mapped[str] = mapped_column(String(40), nullable=False)
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    score_band: Mapped[str] = mapped_column(String(32), nullable=False)
    detector: Mapped[str] = mapped_column(String(80), nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    message_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    message_length: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


def compute_keyed_hash(value: str, secret_key: str) -> str:
    """Compute a 64-character lowercase hex HMAC-SHA256 digest using `secret_key`."""
    if not secret_key or len(secret_key.strip()) < 16:
        raise ValueError("HMAC secret_key must be at least 16 characters.")
    raw_bytes = (value or "").encode("utf-8", errors="replace")
    key_bytes = secret_key.encode("utf-8")
    return hmac.new(key_bytes, raw_bytes, hashlib.sha256).hexdigest()


def build_security_event(
    *,
    request_id: str,
    user_id: str | uuid.UUID,
    layer: str,
    decision: Decision,
    score_band: ScoreBand | str,
    detector: str,
    latency_ms: float,
    policy_version: str,
    mode: Literal["shadow", "enforce"],
    raw_message: str,
    hash_key: str,
) -> SecurityEvent:
    """Create a validated SecurityEvent by hashing `user_id` and `raw_message` via HMAC-SHA256.

    `raw_message` is hashed and measured in memory and immediately discarded; it never enters
    the returned `SecurityEvent` object.
    """
    msg_text = raw_message or ""
    user_str = str(user_id)
    band_val = score_band.value if isinstance(score_band, ScoreBand) else str(score_band)

    return SecurityEvent(
        request_id=request_id,
        user_id_hash=compute_keyed_hash(user_str, hash_key),
        layer=layer,
        decision=decision,
        score_band=band_val,
        detector=detector,
        latency_ms=round(max(0.0, float(latency_ms)), 2),
        policy_version=policy_version,
        mode=mode,
        message_hash=compute_keyed_hash(msg_text, hash_key),
        message_length=len(msg_text),
        created_at=datetime.now(timezone.utc),
    )


def serialize_security_event_json(event: SecurityEvent) -> str:
    """Serialize a SecurityEvent to a deterministic JSON string containing only whitelisted fields."""
    payload = {
        "id": str(event.id),
        "request_id": event.request_id,
        "user_id_hash": event.user_id_hash,
        "layer": event.layer,
        "decision": event.decision.value if isinstance(event.decision, Decision) else str(event.decision),
        "score_band": event.score_band,
        "detector": event.detector,
        "latency_ms": event.latency_ms,
        "policy_version": event.policy_version,
        "mode": event.mode,
        "message_hash": event.message_hash,
        "message_length": event.message_length,
        "created_at": event.created_at.isoformat(),
    }
    assert set(payload.keys()) == _ALLOWED_EVENT_KEYS
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def log_security_event(event: SecurityEvent) -> str:
    """Emit structured JSON log line for `event` and return the serialized JSON string."""
    json_line = serialize_security_event_json(event)
    logger.info(json_line)
    return json_line


async def write_security_event(db: AsyncSession, event: SecurityEvent) -> GuardrailEvent:
    """Persist `SecurityEvent` into the `guardrail_events` table and emit a structured JSON log."""
    log_security_event(event)
    record = GuardrailEvent(
        id=event.id,
        request_id=event.request_id,
        user_id_hash=event.user_id_hash,
        layer=event.layer,
        decision=event.decision.value if isinstance(event.decision, Decision) else str(event.decision),
        score_band=event.score_band,
        detector=event.detector,
        latency_ms=event.latency_ms,
        policy_version=event.policy_version,
        mode=event.mode,
        message_hash=event.message_hash,
        message_length=event.message_length,
        created_at=event.created_at,
    )
    db.add(record)
    await db.flush()
    return record
