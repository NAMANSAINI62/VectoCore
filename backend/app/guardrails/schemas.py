"""Guardrail schemas, decision enums, layer results, verdicts, and security events."""

import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Decision(str, Enum):
    """Canonical guardrail decision outcomes."""

    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    REDACT = "REDACT"
    REQUIRE_REVIEW = "REQUIRE_REVIEW"
    FALLBACK = "FALLBACK"


class LayerMode(str, Enum):
    """Per-layer execution mode."""

    OFF = "off"
    SHADOW = "shadow"
    ENFORCE = "enforce"


class ScoreBand(str, Enum):
    """Coarse severity band recorded in audit logs and events (no raw scores exposed)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    UNAVAILABLE = "unavailable"


class FailMode(str, Enum):
    """Detector failure disposition when a detector times out, errors, or trips breaker."""

    OPEN = "open"
    CLOSED = "closed"


_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


class LayerResult(BaseModel):
    """Outcome produced by a single detector within a guardrail layer."""

    model_config = ConfigDict(extra="forbid")

    layer: str = Field(min_length=1, max_length=40)
    detector: str = Field(min_length=1, max_length=80)
    decision: Decision
    mode: LayerMode = LayerMode.SHADOW
    score_band: ScoreBand = ScoreBand.LOW
    categories: list[str] = Field(default_factory=list)
    latency_ms: float = Field(default=0.0, ge=0.0)
    redacted_text: str | None = None
    degraded: bool = False
    error_code: str | None = None


class GuardrailVerdict(BaseModel):
    """Aggregated decision for a guardrail layer after policy and mode evaluation."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=64)
    layer: str = Field(min_length=1, max_length=40)
    mode: LayerMode = LayerMode.SHADOW
    effective_decision: Decision
    raw_decision: Decision
    policy_version: str = Field(min_length=1, max_length=32)
    latency_ms: float = Field(default=0.0, ge=0.0)
    user_safe_message: str | None = None
    redacted_content: str | None = None
    reason_category: str | None = None
    layer_results: list[LayerResult] = Field(default_factory=list)
    degraded: bool = False


class SecurityEvent(BaseModel):
    """Sanitized security audit event persisted to PostgreSQL and JSON logs.

    Raw user/assistant text is strictly prohibited: `extra="forbid"` rejects any
    unexpected field, and `user_id_hash` / `message_hash` must be 64-char lowercase
    hex HMAC-SHA256 digests.
    """

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    request_id: str = Field(min_length=1, max_length=64)
    user_id_hash: str = Field(min_length=64, max_length=64)
    layer: str = Field(min_length=1, max_length=40)
    decision: Decision
    score_band: str = Field(min_length=1, max_length=32)
    detector: str = Field(min_length=1, max_length=80)
    latency_ms: float = Field(default=0.0, ge=0.0)
    policy_version: str = Field(min_length=1, max_length=32)
    mode: Literal["shadow", "enforce"]
    message_hash: str = Field(min_length=64, max_length=64)
    message_length: int = Field(ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("user_id_hash", "message_hash")
    @classmethod
    def _validate_hex64(cls, value: str) -> str:
        if not _HEX64_RE.match(value):
            raise ValueError("Hash field must be a 64-character lowercase hexadecimal HMAC-SHA256 digest.")
        return value
