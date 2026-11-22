"""FastAPI lifespan initialization, warm-up, health state, and per-detector pybreaker circuit breakers."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import threading
from typing import Any, TypeVar

import pybreaker

from app.guardrails.config.settings import GuardrailsSettings, get_guardrails_settings

T = TypeVar("T")

DETECTOR_NAMES: tuple[str, ...] = (
    "self_check_input",
    "content_safety_input",
    "content_safety_output",
    "presidio_pii",
    "secret_scanner",
)


class DetectorCircuitBreaker:
    """Async-safe and sync-safe circuit breaker backed by `pybreaker.CircuitBreaker`.

    Exposes canonical states (`closed`, `open`, `half-open`), enforces per-call timeouts,
    and delegates state transitions (`closed -> open -> half-open -> closed`) to pybreaker.
    """

    def __init__(
        self,
        name: str,
        fail_max: int = 3,
        reset_timeout: int = 30,
        timeout_sec: float = 4.0,
    ) -> None:
        self.name = name
        self.timeout_sec = timeout_sec
        self._breaker = pybreaker.CircuitBreaker(
            fail_max=fail_max,
            reset_timeout=reset_timeout,
            name=name,
        )
        # Ensure re-entrant lock safety when pybreaker state callbacks transition states
        self._breaker._lock = threading.RLock()

    @property
    def breaker(self) -> pybreaker.CircuitBreaker:
        return self._breaker

    @property
    def current_state(self) -> str:
        """Return 'closed', 'open', or 'half-open'."""
        return str(self._breaker.current_state)

    @property
    def fail_counter(self) -> int:
        return int(self._breaker.fail_counter)

    def open(self) -> None:
        """Manually trip the circuit breaker to 'open'."""
        self._breaker.open()

    def half_open(self) -> None:
        """Manually transition the circuit breaker to 'half-open'."""
        self._breaker.half_open()

    def close(self) -> None:
        """Manually reset the circuit breaker to 'closed'."""
        self._breaker.close()

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Execute a synchronous callable through pybreaker's state machine."""
        return self._breaker.call(func, *args, **kwargs)

    async def call_async(
        self,
        func: Callable[..., Awaitable[T]],
        *args: Any,
        timeout_sec: float | None = None,
        **kwargs: Any,
    ) -> T:
        """Execute an async callable under pybreaker's state machine with an asyncio timeout.

        Uses `pybreaker.CircuitBreakerState.before_call`, `_handle_success`, and
        `_handle_error` directly so asyncio coroutines work without Tornado.
        """
        effective_timeout = timeout_sec if timeout_sec is not None else self.timeout_sec

        with self._breaker._lock:
            if self._breaker.current_state == pybreaker.STATE_OPEN:
                timeout = timedelta(seconds=self._breaker.reset_timeout)
                opened_at = self._breaker._state_storage.opened_at
                if opened_at and datetime.now(UTC) < opened_at + timeout:
                    raise pybreaker.CircuitBreakerError("Timeout not elapsed yet, circuit breaker still open")
                self._breaker.half_open()

            for listener in self._breaker.listeners:
                listener.before_call(self._breaker, func, *args, **kwargs)

        try:
            result = await asyncio.wait_for(func(*args, **kwargs), timeout=effective_timeout)
        except BaseException as exc:
            with self._breaker._lock:
                self._breaker.state._handle_error(exc)
            raise
        else:
            with self._breaker._lock:
                self._breaker.state._handle_success()
            return result


@dataclass
class GuardrailsLifecycleManager:
    """Holds validated settings, warm-up readiness, health state, and per-detector circuit breakers."""

    settings: GuardrailsSettings
    initialized: bool = False
    warmed_up: bool = False
    breakers: dict[str, DetectorCircuitBreaker] = field(default_factory=dict)
    detector_status: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.breakers:
            self.breakers = self._create_breakers(self.settings)
        if not self.detector_status:
            self.detector_status = {
                name: {
                    "state": "UNAVAILABLE",
                    "available": False,
                    "self_test_passed": False,
                    "last_error": None,
                }
                for name in DETECTOR_NAMES
            }

    def record_detector_status(
        self,
        detector: str,
        *,
        available: bool,
        self_test_passed: bool,
        last_error: str | None = None,
    ) -> None:
        """Update startup self-test availability state for a detector."""
        self.detector_status[detector] = {
            "state": "READY" if (available and self_test_passed) else "UNAVAILABLE",
            "available": bool(available),
            "self_test_passed": bool(self_test_passed),
            "last_error": last_error,
        }

    @staticmethod
    def _create_breakers(settings: GuardrailsSettings) -> dict[str, DetectorCircuitBreaker]:
        timeout_map: dict[str, float] = {
            "self_check_input": settings.GUARDRAILS_SELF_CHECK_TIMEOUT_SEC,
            "content_safety_input": settings.GUARDRAILS_CONTENT_SAFETY_TIMEOUT_SEC,
            "content_safety_output": settings.GUARDRAILS_CONTENT_SAFETY_TIMEOUT_SEC,
            "presidio_pii": settings.GUARDRAILS_PII_TIMEOUT_SEC,
            "secret_scanner": settings.GUARDRAILS_SECRET_SCAN_TIMEOUT_SEC,
        }
        return {
            name: DetectorCircuitBreaker(
                name=name,
                fail_max=settings.GUARDRAILS_CB_FAIL_MAX,
                reset_timeout=settings.GUARDRAILS_CB_RESET_TIMEOUT_SEC,
                timeout_sec=timeout_map[name],
            )
            for name in DETECTOR_NAMES
        }

    def get_breaker(self, detector: str) -> DetectorCircuitBreaker:
        if detector not in self.breakers:
            raise KeyError(f"Unknown guardrail detector '{detector}'.")
        return self.breakers[detector]

    async def startup(self) -> None:
        """Validate settings, initialize circuit breakers, and mark warm-up complete."""
        self.initialized = True
        self.warmed_up = True

    async def shutdown(self) -> None:
        """Mark lifecycle shut down cleanly."""
        self.warmed_up = False
        self.initialized = False

    def health_snapshot(self) -> dict[str, Any]:
        """Return non-sensitive health state for internal diagnostics."""
        return {
            "enabled": self.settings.GUARDRAILS_ENABLED,
            "policy_version": self.settings.GUARDRAILS_POLICY_VERSION,
            "initialized": self.initialized,
            "warmed_up": self.warmed_up,
            "modes": {
                "input": self.settings.GUARDRAILS_INPUT_MODE,
                "pii": self.settings.GUARDRAILS_PII_MODE,
                "output": self.settings.GUARDRAILS_OUTPUT_MODE,
                "cache": self.settings.GUARDRAILS_CACHE_MODE,
                "tool": self.settings.GUARDRAILS_TOOL_MODE,
            },
            "breakers": {
                name: {
                    "state": breaker.current_state,
                    "fail_counter": breaker.fail_counter,
                }
                for name, breaker in self.breakers.items()
            },
            "detectors": dict(self.detector_status),
        }


_lifecycle_instance: GuardrailsLifecycleManager | None = None


def get_lifecycle_manager(settings: GuardrailsSettings | None = None) -> GuardrailsLifecycleManager:
    """Return or create the singleton GuardrailsLifecycleManager."""
    global _lifecycle_instance
    if settings is not None:
        _lifecycle_instance = GuardrailsLifecycleManager(settings=settings)
        return _lifecycle_instance
    if _lifecycle_instance is None:
        _lifecycle_instance = GuardrailsLifecycleManager(settings=get_guardrails_settings())
    return _lifecycle_instance
