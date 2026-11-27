"""Configuration settings for the AI Guardrails package."""

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_PATH = Path(__file__).resolve().parent.parent.parent.parent / ".env"

_POLICY_VERSION_RE = re.compile(r"^v\d+\.\d+(\.\d+)?$")

# Models verified in the spike to have reached End-of-Life (HTTP 410) or be invalid
_RETIRED_MODEL_IDS = frozenset({
    "nvidia/llama-3.1-nemoguard-8b-content-safety",
    "nvidia/nemotron-content-safety-reasoning-4b",
    "meta/llama-guard-4-12b",
    "nvidia/nemotron-3.5-content-safety",
})


class GuardrailsSettings(BaseSettings):
    """Pydantic settings governing guardrail modes, timeouts, model IDs, and circuit breakers.

    Every layer defaults to `shadow` mode. Invalid modes, retired model IDs, non-positive
    timeouts, or malformed policy versions fail immediately at startup.
    """

    GUARDRAILS_ENABLED: bool = True
    GUARDRAILS_POLICY_VERSION: str = "v1.0"
    GUARDRAILS_HASH_KEY: str = "default_guardrails_hmac_key_change_in_prod_min_16"

    # Per-layer mode: off | shadow | enforce (every layer defaults to shadow)
    GUARDRAILS_INPUT_MODE: Literal["off", "shadow", "enforce"] = "shadow"
    GUARDRAILS_PII_MODE: Literal["off", "shadow", "enforce"] = "shadow"
    GUARDRAILS_OUTPUT_MODE: Literal["off", "shadow", "enforce"] = "shadow"
    GUARDRAILS_CACHE_MODE: Literal["off", "shadow", "enforce"] = "shadow"
    GUARDRAILS_TOOL_MODE: Literal["off", "shadow", "enforce"] = "shadow"

    # Configurable detector model IDs (never hardcoded in detector logic)
    GUARDRAILS_SELF_CHECK_MODEL_ID: str = "openai/gpt-oss-20b"
    GUARDRAILS_CONTENT_SAFETY_MODEL_ID: str = "nvidia/llama-3.1-nemotron-safety-guard-8b-v3"
    GUARDRAILS_SPACY_MODEL_NAME: str = "en_core_web_sm"

    # Per-detector timeout budgets (seconds)
    GUARDRAILS_SELF_CHECK_TIMEOUT_SEC: float = 4.0
    GUARDRAILS_CONTENT_SAFETY_TIMEOUT_SEC: float = 10.0
    GUARDRAILS_PII_TIMEOUT_SEC: float = 1.0
    GUARDRAILS_SECRET_SCAN_TIMEOUT_SEC: float = 1.0

    # Fail-open / fail-closed policy per detector
    GUARDRAILS_SELF_CHECK_FAIL_MODE: Literal["open", "closed"] = "closed"
    GUARDRAILS_CONTENT_SAFETY_FAIL_MODE: Literal["open", "closed"] = "closed"
    GUARDRAILS_PII_FAIL_MODE: Literal["open", "closed"] = "closed"
    GUARDRAILS_SECRET_SCAN_FAIL_MODE: Literal["open", "closed"] = "closed"

    # Circuit breaker thresholds (pybreaker)
    GUARDRAILS_CB_FAIL_MAX: int = 3
    GUARDRAILS_CB_RESET_TIMEOUT_SEC: int = 30

    # Deterministic input size limit
    GUARDRAILS_MAX_INPUT_CHARS: int = 25000

    # Rate limiting & abuse protection (sized to Groq 8000 TPM / 1000 RPD)
    RATE_LIMIT_USER_RPM: int = 10
    RATE_LIMIT_USER_CONCURRENT_STREAMS: int = 2
    RATE_LIMIT_IP_RPM: int = 60
    RATE_LIMIT_REQUEST_DEADLINE_SEC: float = 60.0
    RATE_LIMIT_FAIL_OPEN: bool = True

    @field_validator("GUARDRAILS_POLICY_VERSION")
    @classmethod
    def _validate_policy_version(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not _POLICY_VERSION_RE.match(cleaned):
            raise ValueError(
                f"Invalid GUARDRAILS_POLICY_VERSION '{value}'. Must match 'v<major>.<minor>[.<patch>]'."
            )
        return cleaned

    @field_validator("GUARDRAILS_HASH_KEY")
    @classmethod
    def _validate_hash_key(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if len(cleaned) < 16:
            raise ValueError("GUARDRAILS_HASH_KEY must be at least 16 characters long.")
        return cleaned

    @field_validator("GUARDRAILS_SELF_CHECK_MODEL_ID", "GUARDRAILS_CONTENT_SAFETY_MODEL_ID")
    @classmethod
    def _validate_model_id(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned or "/" not in cleaned:
            raise ValueError(f"Detector model ID '{value}' must be a non-empty '<org>/<model>' identifier.")
        if cleaned in _RETIRED_MODEL_IDS:
            raise ValueError(f"Detector model ID '{cleaned}' is retired/EOL and cannot be configured.")
        return cleaned

    @field_validator("GUARDRAILS_SPACY_MODEL_NAME")
    @classmethod
    def _validate_spacy_model(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("GUARDRAILS_SPACY_MODEL_NAME cannot be empty.")
        if cleaned == "en_core_web_lg":
            raise ValueError("en_core_web_lg is prohibited on constrained RAM; use en_core_web_sm.")
        return cleaned

    @field_validator(
        "GUARDRAILS_SELF_CHECK_TIMEOUT_SEC",
        "GUARDRAILS_CONTENT_SAFETY_TIMEOUT_SEC",
        "GUARDRAILS_PII_TIMEOUT_SEC",
        "GUARDRAILS_SECRET_SCAN_TIMEOUT_SEC",
    )
    @classmethod
    def _validate_timeouts(cls, value: float) -> float:
        if value <= 0.0 or value > 30.0:
            raise ValueError(f"Detector timeout must be > 0 and <= 30.0 seconds, got {value}.")
        return value

    @field_validator("GUARDRAILS_CB_FAIL_MAX", "GUARDRAILS_CB_RESET_TIMEOUT_SEC")
    @classmethod
    def _validate_circuit_breaker_params(cls, value: int) -> int:
        if value < 1:
            raise ValueError(f"Circuit breaker threshold/timeout must be >= 1, got {value}.")
        return value

    @field_validator("GUARDRAILS_MAX_INPUT_CHARS")
    @classmethod
    def _validate_max_input_chars(cls, value: int) -> int:
        if value < 1 or value > 100000:
            raise ValueError(f"GUARDRAILS_MAX_INPUT_CHARS must be between 1 and 100000, got {value}.")
        return value

    @model_validator(mode="after")
    def _validate_layer_modes(self) -> "GuardrailsSettings":
        for attr in (
            "GUARDRAILS_INPUT_MODE",
            "GUARDRAILS_PII_MODE",
            "GUARDRAILS_OUTPUT_MODE",
            "GUARDRAILS_CACHE_MODE",
            "GUARDRAILS_TOOL_MODE",
        ):
            val = getattr(self, attr)
            if val not in ("off", "shadow", "enforce"):
                raise ValueError(f"Invalid layer mode for {attr}: {val}")
        return self

    def get_layer_mode(self, layer: str) -> Literal["off", "shadow", "enforce"]:
        """Return configured mode for a canonical layer name."""
        mapping: dict[str, Literal["off", "shadow", "enforce"]] = {
            "input": self.GUARDRAILS_INPUT_MODE,
            "pii": self.GUARDRAILS_PII_MODE,
            "output": self.GUARDRAILS_OUTPUT_MODE,
            "cache": self.GUARDRAILS_CACHE_MODE,
            "tool": self.GUARDRAILS_TOOL_MODE,
        }
        if layer not in mapping:
            raise ValueError(f"Unknown guardrail layer '{layer}'.")
        return mapping[layer]

    model_config = SettingsConfigDict(
        env_file=str(_ENV_PATH),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache
def get_guardrails_settings() -> GuardrailsSettings:
    """Return cached GuardrailsSettings instance, failing immediately if invalid."""
    return GuardrailsSettings()
