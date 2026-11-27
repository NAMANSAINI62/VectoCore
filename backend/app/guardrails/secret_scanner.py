"""Deterministic secret scanner using detect-secrets, hashed env-secret fingerprints, and canary tokens.

Never logs, stores, or exposes raw secret values; only variable names or secret categories
are tracked internally, and plaintext secrets from env are hashed in memory with an
ephemeral per-process HMAC key.
"""

import asyncio
import hashlib
import hmac
import os
import re
import threading
import time
from typing import Any
from urllib.parse import urlparse

import pybreaker
from detect_secrets.core.scan import scan_line
from detect_secrets.settings import default_settings

from app.guardrails.config.settings import GuardrailsSettings, get_guardrails_settings
from app.guardrails.schemas import Decision, LayerMode, LayerResult, ScoreBand

_DETECT_SECRETS_LOCK = threading.Lock()

# Names of application secret environment variables fingerprinted at startup (values never stored in plaintext)
APP_SECRET_ENV_NAMES: tuple[str, ...] = (
    "SECRET_KEY",
    "JWT_SECRET_KEY",
    "POSTGRES_PASSWORD",
    "DATABASE_URL",
    "REDIS_URL",
    "OPENROUTER_API_KEY",
    "GROQ_API_KEY",
    "GEMINI_API_KEY",
    "COHERE_API_KEY",
    "NVIDIA_API_KEY",
    "NVIDIA_EMBED_API_KEY",
    "BREVO_API_KEY",
    "TAVILY_API_KEY",
    "GOOGLE_CLIENT_SECRET",
    "SMTP_PASSWORD",
    "GUARDRAILS_HASH_KEY",
)

# Provider API key prefix formats (deterministic structure check, not attack phrases)
_STRUCTURED_KEY_PREFIX_RE = re.compile(
    r"\b(?:"
    r"nvapi-[A-Za-z0-9_\-]{20,}"
    r"|gsk_[A-Za-z0-9]{20,}"
    r"|sk-(?:proj-|live-|test-)?[A-Za-z0-9_\-]{20,}"
    r"|AIza[0-9A-Za-z_\-]{35}"
    r"|gh[pousr]_[A-Za-z0-9_]{24,}"
    r"|glpat-[A-Za-z0-9_\-]{20,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|xox[baprs]-[A-Za-z0-9\-]{16,}"
    r")\b"
)

_TOKEN_SPLIT_RE = re.compile(r"[\s\"'`,;()\[\]{}<>=]+")


class SecretScannerDetector:
    """Deterministic credential, env-secret fingerprint, and canary token scanner."""

    detector_name: str = "secret_scanner"

    def __init__(
        self,
        settings: GuardrailsSettings | None = None,
        breaker: Any | None = None,
        extra_named_secrets: dict[str, str] | None = None,
        canaries: list[str] | None = None,
    ) -> None:
        self.settings = settings or get_guardrails_settings()
        self._breaker = breaker or pybreaker.CircuitBreaker(
            fail_max=self.settings.GUARDRAILS_CB_FAIL_MAX,
            reset_timeout=self.settings.GUARDRAILS_CB_RESET_TIMEOUT_SEC,
            name=self.detector_name,
        )
        self._ephemeral_key: bytes = os.urandom(32)
        # Maps HMAC-SHA256 digest -> secret variable name (never stores raw secret values)
        self._secret_fingerprints: dict[str, str] = {}
        self._secret_lengths: set[int] = set()
        # Maps HMAC-SHA256 digest -> canary label
        self._canary_fingerprints: dict[str, str] = {}
        self._canary_lengths: set[int] = set()

        self.available: bool = False
        self.self_test_passed: bool = False
        self.last_error: str | None = None

        self._load_env_fingerprints(extra_named_secrets=extra_named_secrets)
        for idx, canary in enumerate(canaries or ["CANARY-GUARDRAIL-7F9A2C1E-DO-NOT-REVEAL"]):
            self.register_canary(canary, label=f"canary_{idx}")

    def _digest(self, value: str) -> str:
        return hmac.new(self._ephemeral_key, value.encode("utf-8", errors="replace"), hashlib.sha256).hexdigest()

    def register_secret_value(self, var_name: str, raw_secret: str) -> None:
        """Hash `raw_secret` in memory and record its digest and length without storing `raw_secret`."""
        cleaned = (raw_secret or "").strip()
        if len(cleaned) < 8:
            return
        self._secret_fingerprints[self._digest(cleaned)] = var_name
        self._secret_lengths.add(len(cleaned))

        # If the secret is a connection URL with embedded password, fingerprint the password too
        if "://" in cleaned:
            try:
                parsed = urlparse(cleaned)
                if parsed.password and len(parsed.password) >= 8:
                    self._secret_fingerprints[self._digest(parsed.password)] = f"{var_name}_PASSWORD"
                    self._secret_lengths.add(len(parsed.password))
            except Exception:
                pass

    def register_canary(self, canary_token: str, label: str = "system_canary") -> None:
        """Hash a canary token in memory for exact canary leak matching."""
        cleaned = (canary_token or "").strip()
        if len(cleaned) < 6:
            return
        self._canary_fingerprints[self._digest(cleaned)] = label
        self._canary_lengths.add(len(cleaned))

    def _load_env_fingerprints(self, extra_named_secrets: dict[str, str] | None = None) -> None:
        for env_name in APP_SECRET_ENV_NAMES:
            val = os.environ.get(env_name, "")
            if val:
                self.register_secret_value(env_name, val)
        if extra_named_secrets:
            for name, val in extra_named_secrets.items():
                self.register_secret_value(name, val)

    def _scan_text_sync(self, text: str) -> list[str]:
        if not text or not text.strip():
            return []

        categories: set[str] = set()

        # 1. Exact candidate token and sliding-window HMAC comparison for canaries & app env secrets
        tokens = [tok for tok in _TOKEN_SPLIT_RE.split(text) if len(tok) >= 6]
        for tok in tokens:
            d = self._digest(tok)
            if d in self._canary_fingerprints:
                categories.add("canary_token_leak")
            if d in self._secret_fingerprints:
                categories.add("env_secret_leak")

        # Check sliding windows for registered secret/canary lengths in case secret is embedded without whitespace
        text_len = len(text)
        for length in self._canary_lengths:
            if length <= text_len <= 32768:
                for i in range(0, text_len - length + 1):
                    if self._digest(text[i : i + length]) in self._canary_fingerprints:
                        categories.add("canary_token_leak")
                        break

        for length in self._secret_lengths:
            if length <= text_len <= 32768 and "env_secret_leak" not in categories:
                for i in range(0, text_len - length + 1):
                    if self._digest(text[i : i + length]) in self._secret_fingerprints:
                        categories.add("env_secret_leak")
                        break

        # 2. Structured provider API key prefixes (nvapi-, gsk_, sk-, AIza, ghp_, AKIA, etc.)
        if _STRUCTURED_KEY_PREFIX_RE.search(text):
            categories.add("api_key_format")

        # 3. detect-secrets plugin scan line-by-line
        with _DETECT_SECRETS_LOCK:
            with default_settings():
                for line in text.splitlines():
                    if not line.strip():
                        continue
                    for secret in scan_line(line):
                        # High-entropy plugins alone can trigger on non-secret text unless paired or assignment-like;
                        # keep all format-specific detectors and high-entropy matches on assignment/key contexts
                        sec_type = secret.type
                        if sec_type in ("Base64 High Entropy String", "Hex High Entropy String"):
                            val = getattr(secret, "secret_value", "") or ""
                            if val.startswith(("http://", "https://")):
                                continue
                            if re.search(
                                r"(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|secret|bearer|authorization)\s*(?:[:=]\s*|\s+Bearer\s+)\S+",
                                line,
                                re.IGNORECASE,
                            ):
                                categories.add("high_entropy_secret")
                        else:
                            categories.add(f"detect_secrets:{sec_type.lower().replace(' ', '_')}")

        return sorted(categories)

    def redact_secrets(self, text: str) -> str:
        """Replace detected API keys, registered env-secret fingerprints, and canaries with `<REDACTED_SECRET>`."""
        if not text:
            return text
        redacted = _STRUCTURED_KEY_PREFIX_RE.sub("<REDACTED_SECRET>", text)

        # Redact exact sliding-window matches of registered env secrets or canaries
        all_lengths = sorted(self._secret_lengths | self._canary_lengths, reverse=True)
        for length in all_lengths:
            if 6 <= length <= len(redacted) <= 32768:
                i = 0
                chunks: list[str] = []
                while i <= len(redacted) - length:
                    candidate = redacted[i : i + length]
                    digest = self._digest(candidate)
                    if digest in self._secret_fingerprints or digest in self._canary_fingerprints:
                        chunks.append("<REDACTED_SECRET>")
                        i += length
                    else:
                        chunks.append(redacted[i])
                        i += 1
                if i < len(redacted):
                    chunks.append(redacted[i:])
                redacted = "".join(chunks)

        # Redact detect-secrets secret_value matches line-by-line
        with _DETECT_SECRETS_LOCK:
            with default_settings():
                lines = redacted.splitlines(keepends=True)
                out_lines: list[str] = []
                for line in lines:
                    if not line.strip():
                        out_lines.append(line)
                        continue
                    modified = line
                    for secret in scan_line(line):
                        sec_type = secret.type
                        if sec_type in ("Base64 High Entropy String", "Hex High Entropy String"):
                            if not any(
                                k in line.lower()
                                for k in ("key", "token", "secret", "password", "bearer", "auth")
                            ):
                                continue
                        sec_val = getattr(secret, "secret_value", None)
                        if (
                            isinstance(sec_val, str)
                            and len(sec_val) >= 12
                            and not (sec_val.startswith("<") and sec_val.endswith(">"))
                            and sec_val in modified
                        ):
                            modified = modified.replace(sec_val, "<REDACTED_SECRET>")
                    out_lines.append(modified)
                redacted = "".join(out_lines)
        return redacted

    async def _invoke_under_breaker(self, text: str, timeout_sec: float) -> list[str]:
        if hasattr(self._breaker, "call_async") and hasattr(self._breaker, "timeout_sec"):
            return await self._breaker.call_async(
                asyncio.to_thread,
                self._scan_text_sync,
                text,
                timeout_sec=timeout_sec,
            )
        return await asyncio.wait_for(
            asyncio.to_thread(self._breaker.call, self._scan_text_sync, text),
            timeout=timeout_sec,
        )

    async def check(
        self,
        text: str,
        *,
        layer: str = "input",
        mode: LayerMode | None = None,
        require_available: bool = True,
    ) -> LayerResult:
        """Scan `text` for secrets or canary leaks under timeout and circuit breaker."""
        effective_mode = mode or LayerMode(self.settings.get_layer_mode(layer if layer in ("input", "output") else "input"))
        t0 = time.perf_counter()

        if require_available and not self.available:
            dt_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            fail_decision = (
                Decision.ALLOW
                if self.settings.GUARDRAILS_SECRET_SCAN_FAIL_MODE == "open"
                else Decision.FALLBACK
            )
            return LayerResult(
                layer=layer,
                detector=self.detector_name,
                decision=fail_decision,
                mode=effective_mode,
                score_band=ScoreBand.UNAVAILABLE,
                categories=[],
                latency_ms=dt_ms,
                degraded=True,
                error_code="detector_unavailable",
            )

        try:
            categories = await self._invoke_under_breaker(
                text, self.settings.GUARDRAILS_SECRET_SCAN_TIMEOUT_SEC
            )
            dt_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            if categories:
                decision = (
                    Decision.FALLBACK
                    if layer in ("input", "pii")
                    else Decision.BLOCK
                )
                redacted_val = self.redact_secrets(text)
                return LayerResult(
                    layer=layer,
                    detector=self.detector_name,
                    decision=decision,
                    mode=effective_mode,
                    score_band=ScoreBand.CRITICAL,
                    categories=categories,
                    latency_ms=dt_ms,
                    redacted_text=redacted_val if redacted_val != text else None,
                    degraded=False,
                )
            return LayerResult(
                layer=layer,
                detector=self.detector_name,
                decision=Decision.ALLOW,
                mode=effective_mode,
                score_band=ScoreBand.LOW,
                categories=[],
                latency_ms=dt_ms,
                degraded=False,
            )
        except BaseException as exc:
            dt_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            err_code = "circuit_open" if isinstance(exc, pybreaker.CircuitBreakerError) else (
                "timeout" if isinstance(exc, asyncio.TimeoutError) else "detector_error"
            )
            fail_decision = (
                Decision.ALLOW
                if self.settings.GUARDRAILS_SECRET_SCAN_FAIL_MODE == "open"
                else Decision.FALLBACK
            )
            return LayerResult(
                layer=layer,
                detector=self.detector_name,
                decision=fail_decision,
                mode=effective_mode,
                score_band=ScoreBand.UNAVAILABLE,
                categories=[],
                latency_ms=dt_ms,
                degraded=True,
                error_code=err_code,
            )

    async def self_test(self) -> bool:
        """Startup self-test: 1 fake credential probe must block/fallback and 1 benign probe must allow."""
        try:
            harmful_probe = "aws_access_key_id = AKIAIOSFODNN7EXAMPLE"
            benign_probe = "Explain how Redis L1 exact hashing and PostgreSQL pgvector work."

            harmful_res = await self.check(harmful_probe, layer="input", require_available=False)
            benign_res = await self.check(benign_probe, layer="input", require_available=False)

            if (
                not harmful_res.degraded
                and harmful_res.decision in (Decision.BLOCK, Decision.FALLBACK)
                and not benign_res.degraded
                and benign_res.decision == Decision.ALLOW
            ):
                self.available = True
                self.self_test_passed = True
                self.last_error = None
                return True

            self.available = False
            self.self_test_passed = False
            self.last_error = (
                f"Self-test mismatch: secret_probe={harmful_res.decision}, benign_probe={benign_res.decision}"
            )
            return False
        except BaseException as exc:
            self.available = False
            self.self_test_passed = False
            self.last_error = f"{type(exc).__name__}"
            return False
