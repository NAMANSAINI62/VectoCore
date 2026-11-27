"""Public GuardrailsService facade orchestrating detectors, lifecycle, and decision engine."""

import asyncio
import logging
import re
import secrets
import time
import unicodedata
import uuid
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.guardrails.config.settings import GuardrailsSettings, get_guardrails_settings
from app.guardrails.content_safety import ContentSafetyDetector
from app.guardrails.decision_engine import DecisionEngine
from app.guardrails.events import build_security_event, log_security_event, write_security_event
from app.guardrails.injection_jailbreak import InjectionJailbreakDetector
from app.guardrails.lifecycle import GuardrailsLifecycleManager, get_lifecycle_manager
from app.guardrails.privacy import PrivacyDetector
from app.guardrails.schemas import Decision, GuardrailVerdict, LayerMode, LayerResult, ScoreBand
from app.guardrails.secret_scanner import SecretScannerDetector

logger = logging.getLogger(__name__)
DEFAULT_INPUT_MAX_CHARS = 25000
DEFAULT_OUTPUT_MAX_CHARS = 32000


class _OutputResponseSchema(BaseModel):
    """Pydantic validation schema for assistant output before streaming/caching."""

    content: str = Field(min_length=1, max_length=DEFAULT_OUTPUT_MAX_CHARS)

# Zero-width, BOM, directional formatting, and C0/C1 control characters (preserving \n, \r, \t)
_ZERO_WIDTH_OR_CONTROL_RE = re.compile(
    r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f"
    r"\u00ad\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]"
)


def normalize_input_text(text: str, max_chars: int = DEFAULT_INPUT_MAX_CHARS) -> tuple[str, bool]:
    """Normalize user input before guardrail detection.

    1. Unicode NFKC normalization (folds full-width/compatibility chars to canonical forms).
    2. Strip zero-width characters, soft hyphens, bidirectional overrides, and C0/C1 control chars
       (while preserving standard newlines and tabs).
    3. Check size cap (`max_chars`, default 12000 matching ChatCompletionRequest).
    Returns `(normalized_text, within_size_cap)`.
    """
    normalized = unicodedata.normalize("NFKC", text or "")
    cleaned = _ZERO_WIDTH_OR_CONTROL_RE.sub("", normalized).strip()
    return cleaned, len(cleaned) <= max_chars


class GuardrailsService:
    """Single application entrypoint for guardrail checks, detector self-tests, and lifecycle."""

    def __init__(
        self,
        settings: GuardrailsSettings | None = None,
        lifecycle: GuardrailsLifecycleManager | None = None,
        decision_engine: DecisionEngine | None = None,
        injection_detector: InjectionJailbreakDetector | None = None,
        content_safety_detector: ContentSafetyDetector | None = None,
        privacy_detector: PrivacyDetector | None = None,
        secret_scanner_detector: SecretScannerDetector | None = None,
    ) -> None:
        self.settings = settings or get_guardrails_settings()
        self.lifecycle = lifecycle or get_lifecycle_manager(self.settings)
        self.decision_engine = decision_engine or DecisionEngine()

        self.injection_detector = injection_detector or InjectionJailbreakDetector(
            settings=self.settings,
            breaker=self.lifecycle.get_breaker("self_check_input"),
        )
        self.content_safety_detector = content_safety_detector or ContentSafetyDetector(
            settings=self.settings,
            breaker=self.lifecycle.get_breaker("content_safety_input"),
        )
        self.privacy_detector = privacy_detector or PrivacyDetector(
            settings=self.settings,
            breaker=self.lifecycle.get_breaker("presidio_pii"),
        )
        self.secret_scanner_detector = secret_scanner_detector or SecretScannerDetector(
            settings=self.settings,
            breaker=self.lifecycle.get_breaker("secret_scanner"),
        )
        # Generate a random per-process canary token at startup (never logged in full)
        self._runtime_canary: str = f"CANARY-{secrets.token_hex(8).upper()}"
        self.secret_scanner_detector.register_canary(self._runtime_canary, label="runtime_system_canary")

    def get_runtime_canary(self) -> str:
        """Return the per-process runtime canary token for system prompt integrity."""
        return self._runtime_canary

    async def run_self_tests(self) -> dict[str, bool]:
        """Run startup self-tests across all detectors in parallel and record health in lifecycle."""
        ij_ok, cs_ok, pii_ok, sec_ok = await asyncio.gather(
            self.injection_detector.self_test(),
            self.content_safety_detector.self_test(),
            self.privacy_detector.self_test(),
            self.secret_scanner_detector.self_test(),
        )

        self.lifecycle.record_detector_status(
            "self_check_input",
            available=self.injection_detector.available,
            self_test_passed=ij_ok,
            last_error=self.injection_detector.last_error,
        )
        self.lifecycle.record_detector_status(
            "content_safety_input",
            available=self.content_safety_detector.available,
            self_test_passed=cs_ok,
            last_error=self.content_safety_detector.last_error,
        )
        self.lifecycle.record_detector_status(
            "content_safety_output",
            available=self.content_safety_detector.available,
            self_test_passed=cs_ok,
            last_error=self.content_safety_detector.last_error,
        )
        self.lifecycle.record_detector_status(
            "presidio_pii",
            available=self.privacy_detector.available,
            self_test_passed=pii_ok,
            last_error=self.privacy_detector.last_error,
        )
        self.lifecycle.record_detector_status(
            "secret_scanner",
            available=self.secret_scanner_detector.available,
            self_test_passed=sec_ok,
            last_error=self.secret_scanner_detector.last_error,
        )
        return {
            "self_check_input": ij_ok,
            "content_safety_input": cs_ok,
            "presidio_pii": pii_ok,
            "secret_scanner": sec_ok,
        }

    async def startup(self, run_self_tests: bool = False) -> None:
        """Initialize lifecycle, optionally run detector self-tests, and log per-detector status."""
        await self.lifecycle.startup()
        if run_self_tests:
            await self.run_self_tests()
            log = logging.getLogger("app.guardrails.startup")
            unavailable: list[str] = []
            for name, info in self.lifecycle.detector_status.items():
                state = info.get("state", "UNAVAILABLE")
                reason = info.get("last_error") or "ok"
                log.info("Guardrails detector [%s]: %s (reason=%s)", name, state, reason)
                if state != "READY":
                    unavailable.append(f"{name}={reason}")
            if unavailable:
                log.warning(
                    "GUARDRAILS WARNING: %d detector(s) UNAVAILABLE at startup: %s",
                    len(unavailable),
                    "; ".join(unavailable),
                )
            in_unavail = (
                self.lifecycle.detector_status.get("self_check_input", {}).get("state") != "READY"
                and self.lifecycle.detector_status.get("content_safety_input", {}).get("state") != "READY"
            )
            if in_unavail and self.settings.GUARDRAILS_INPUT_MODE == "enforce":
                log.error(
                    "GUARDRAILS ERROR: Both input detectors (self_check_input, content_safety_input) are UNAVAILABLE while GUARDRAILS_INPUT_MODE=enforce!"
                )

    async def shutdown(self) -> None:
        """Clean up guardrails resources during FastAPI lifespan shutdown."""
        await self.lifecycle.shutdown()

    def health_snapshot(self) -> dict[str, Any]:
        """Return non-sensitive health and circuit-breaker status."""
        return self.lifecycle.health_snapshot()

    async def _emit_security_events(
        self,
        *,
        request_id: str,
        user_id: str | uuid.UUID | None,
        raw_message: str,
        results: list[LayerResult],
        db: AsyncSession | None = None,
    ) -> None:
        """Emit structured JSON log and persist `guardrail_events` rows for triggered/degraded detectors."""
        user_str = str(user_id or "anonymous")
        for res in results:
            if res.mode == LayerMode.OFF:
                continue
            if res.decision == Decision.ALLOW and not res.degraded:
                continue
            event_mode = "enforce" if res.mode == LayerMode.ENFORCE else "shadow"
            event = build_security_event(
                request_id=request_id,
                user_id=user_str,
                layer=res.layer,
                decision=res.decision,
                score_band=res.score_band,
                detector=res.detector,
                latency_ms=res.latency_ms,
                policy_version=self.settings.GUARDRAILS_POLICY_VERSION,
                mode=event_mode,
                raw_message=raw_message,
                hash_key=self.settings.GUARDRAILS_HASH_KEY,
            )
            if db is not None:
                try:
                    await write_security_event(db, event)
                except Exception as exc:
                    logger.warning(
                        "Best-effort guardrail_events DB write failed (type=%s, error=%s); continuing.",
                        type(exc).__name__,
                        str(exc),
                    )
            else:
                log_security_event(event)

    async def check_input(
        self,
        text: str,
        *,
        request_id: str | None = None,
        user_id: str | uuid.UUID | None = None,
        db: AsyncSession | None = None,
        max_chars: int = DEFAULT_INPUT_MAX_CHARS,
    ) -> GuardrailVerdict:
        """Normalize user input, run Tier-1 + PII/secret detectors in parallel, evaluate policy, and record security events."""
        t0 = time.perf_counter()
        req_id = request_id or uuid.uuid4().hex
        in_mode = LayerMode(self.settings.get_layer_mode("input"))
        pii_mode = LayerMode(self.settings.get_layer_mode("pii"))

        clean_text, within_cap = normalize_input_text(text, max_chars=max_chars)

        if not self.settings.GUARDRAILS_ENABLED or (in_mode == LayerMode.OFF and pii_mode == LayerMode.OFF):
            return GuardrailVerdict(
                request_id=req_id,
                layer="input",
                mode=in_mode,
                effective_decision=Decision.ALLOW,
                raw_decision=Decision.ALLOW,
                policy_version=self.settings.GUARDRAILS_POLICY_VERSION,
                latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                user_safe_message=None,
                redacted_content=clean_text,
                reason_category=None,
                layer_results=[],
                degraded=False,
            )

        if not within_cap:
            dt_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            size_res = LayerResult(
                layer="input",
                detector="input_normalizer",
                decision=Decision.FALLBACK,
                mode=in_mode if in_mode != LayerMode.OFF else pii_mode,
                score_band=ScoreBand.HIGH,
                categories=["input_size_exceeded"],
                latency_ms=dt_ms,
                degraded=False,
            )
            verdict = self.decision_engine.evaluate(
                request_id=req_id,
                layer="input",
                mode=size_res.mode,
                results=[size_res],
                policy_version=self.settings.GUARDRAILS_POLICY_VERSION,
                guardrails_enabled=self.settings.GUARDRAILS_ENABLED,
            )
            await self._emit_security_events(
                request_id=req_id,
                user_id=user_id,
                raw_message=text or "",
                results=[size_res],
                db=db,
            )
            return verdict

        # Step 1 (Privacy ordering): Run local Presidio PII and SecretScanner FIRST (~20 ms)
        # so raw Aadhaar, PAN, phone, email, card numbers, and keys are never sent to Groq or NVIDIA.
        result_map: dict[str, LayerResult] = {}
        if pii_mode != LayerMode.OFF:
            pii_res_raw, sec_res_raw = await asyncio.gather(
                self.privacy_detector.check(clean_text, layer="pii", mode=pii_mode),
                self.secret_scanner_detector.check(clean_text, layer="pii", mode=pii_mode),
            )
            result_map["pii"] = pii_res_raw
            result_map["sec"] = sec_res_raw

        pii_results: list[LayerResult] = [
            result_map[k] for k in ("pii", "sec") if k in result_map
        ]

        # Compose combined redacted text before calling remote input safety detectors
        combined_redacted = clean_text
        pii_redacted_changed = False
        pii_res = result_map.get("pii")
        sec_res = result_map.get("sec")
        if pii_res is not None and pii_res.redacted_text and pii_res.redacted_text != clean_text:
            combined_redacted = pii_res.redacted_text
            pii_redacted_changed = True
        if sec_res is not None and sec_res.categories:
            after_sec = self.secret_scanner_detector.redact_secrets(combined_redacted)
            if after_sec != combined_redacted:
                combined_redacted = after_sec
                pii_redacted_changed = True
            if pii_redacted_changed:
                idx = pii_results.index(sec_res)
                pii_results[idx] = sec_res.model_copy(update={"redacted_text": combined_redacted})
        elif pii_redacted_changed and pii_res is not None:
            idx = pii_results.index(pii_res)
            pii_results[idx] = pii_res.model_copy(update={"redacted_text": combined_redacted})

        # Step 2: Send the REDACTED text to self_check_input and content_safety_input in parallel
        if in_mode != LayerMode.OFF:
            res_ij, res_cs = await asyncio.gather(
                self.injection_detector.check(combined_redacted, layer="input", mode=in_mode),
                self.content_safety_detector.check_input(combined_redacted, mode=in_mode),
            )
            result_map["ij"] = res_ij
            result_map["cs"] = res_cs

        in_results: list[LayerResult] = [
            result_map[k] for k in ("ij", "cs") if k in result_map
        ]

        # If secret_scanner detected a system leak (canary or app env secret) and input layer is active,
        # also treat it as an input-layer critical block/fallback.
        if (
            sec_res is not None
            and in_mode != LayerMode.OFF
            and any(c in ("canary_token_leak", "env_secret_leak") for c in sec_res.categories)
        ):
            in_results.append(
                sec_res.model_copy(
                    update={
                        "layer": "input",
                        "mode": in_mode,
                        "decision": Decision.FALLBACK,
                    }
                )
            )

        in_verdict = self.decision_engine.evaluate(
            request_id=req_id,
            layer="input",
            mode=in_mode,
            results=in_results,
            policy_version=self.settings.GUARDRAILS_POLICY_VERSION,
            guardrails_enabled=self.settings.GUARDRAILS_ENABLED,
        )
        pii_verdict = self.decision_engine.evaluate(
            request_id=req_id,
            layer="pii",
            mode=pii_mode,
            results=pii_results,
            policy_version=self.settings.GUARDRAILS_POLICY_VERSION,
            guardrails_enabled=self.settings.GUARDRAILS_ENABLED,
        )

        all_results = in_verdict.layer_results + pii_verdict.layer_results
        await self._emit_security_events(
            request_id=req_id,
            user_id=user_id,
            raw_message=clean_text,
            results=all_results,
            db=db,
        )

        wall_ms = round((time.perf_counter() - t0) * 1000.0, 2)

        # Combine input verdict and pii verdict respecting each layer's independent mode
        if in_verdict.effective_decision in (Decision.BLOCK, Decision.FALLBACK, Decision.REQUIRE_REVIEW):
            return in_verdict.model_copy(
                update={
                    "latency_ms": wall_ms,
                    "layer_results": all_results,
                    "degraded": in_verdict.degraded or pii_verdict.degraded,
                }
            )
        if pii_verdict.effective_decision in (Decision.BLOCK, Decision.FALLBACK, Decision.REQUIRE_REVIEW):
            return pii_verdict.model_copy(
                update={
                    "layer": "input",
                    "latency_ms": wall_ms,
                    "layer_results": all_results,
                    "degraded": in_verdict.degraded or pii_verdict.degraded,
                }
            )
        if pii_verdict.effective_decision == Decision.REDACT or in_verdict.effective_decision == Decision.REDACT:
            effective_redacted = (
                pii_verdict.redacted_content
                or in_verdict.redacted_content
                or (combined_redacted if pii_redacted_changed else clean_text)
            )
            raw_dec = (
                in_verdict.raw_decision
                if in_verdict.raw_decision in (Decision.BLOCK, Decision.FALLBACK)
                else Decision.REDACT
            )
            return GuardrailVerdict(
                request_id=req_id,
                layer="input",
                mode=pii_mode if pii_verdict.effective_decision == Decision.REDACT else in_mode,
                effective_decision=Decision.REDACT,
                raw_decision=raw_dec,
                policy_version=self.settings.GUARDRAILS_POLICY_VERSION,
                latency_ms=wall_ms,
                user_safe_message=None,
                redacted_content=effective_redacted,
                reason_category=pii_verdict.reason_category or in_verdict.reason_category or "pii_redacted",
                layer_results=all_results,
                degraded=in_verdict.degraded or pii_verdict.degraded,
            )

        # Effective ALLOW (either genuinely clean or running in shadow mode)
        raw_dec = in_verdict.raw_decision if in_verdict.raw_decision != Decision.ALLOW else pii_verdict.raw_decision
        return GuardrailVerdict(
            request_id=req_id,
            layer="input",
            mode=in_mode,
            effective_decision=Decision.ALLOW,
            raw_decision=raw_dec,
            policy_version=self.settings.GUARDRAILS_POLICY_VERSION,
            latency_ms=wall_ms,
            user_safe_message=None,
            redacted_content=clean_text,
            reason_category=None,
            layer_results=all_results,
            degraded=in_verdict.degraded or pii_verdict.degraded,
        )

    async def check_output(
        self,
        user_text: str,
        assistant_text: str,
        *,
        request_id: str | None = None,
        user_id: str | uuid.UUID | None = None,
        db: AsyncSession | None = None,
    ) -> GuardrailVerdict:
        """Run Step 5 output validation: secret/canary scan, content safety (output), Presidio redaction, and Pydantic validation."""
        t0 = time.perf_counter()
        req_id = request_id or uuid.uuid4().hex
        out_mode = LayerMode(self.settings.get_layer_mode("output"))
        pii_mode = LayerMode(self.settings.get_layer_mode("pii"))

        if not self.settings.GUARDRAILS_ENABLED or (out_mode == LayerMode.OFF and pii_mode == LayerMode.OFF):
            return GuardrailVerdict(
                request_id=req_id,
                layer="output",
                mode=out_mode,
                effective_decision=Decision.ALLOW,
                raw_decision=Decision.ALLOW,
                policy_version=self.settings.GUARDRAILS_POLICY_VERSION,
                latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                user_safe_message=None,
                redacted_content=assistant_text,
                reason_category=None,
                layer_results=[],
                degraded=False,
            )

        out_results: list[LayerResult] = []
        pii_results: list[LayerResult] = []

        # 1. Secret / canary scan (runs on output)
        if out_mode != LayerMode.OFF:
            sec_res = await self.secret_scanner_detector.check(assistant_text, layer="output", mode=out_mode)
            out_results.append(sec_res)

        # 2. Content safety (output)
        if out_mode != LayerMode.OFF:
            cs_res = await self.content_safety_detector.check_output(user_text, assistant_text, mode=out_mode)
            out_results.append(cs_res)

        # 3. Presidio redaction (structured entities only)
        if pii_mode != LayerMode.OFF:
            pii_res = await self.privacy_detector.check(assistant_text, layer="pii", mode=pii_mode)
            pii_results.append(pii_res)

        # 4. Pydantic validation
        if out_mode != LayerMode.OFF:
            try:
                _OutputResponseSchema(content=(assistant_text or "").strip())
            except Exception:
                out_results.append(
                    LayerResult(
                        layer="output",
                        detector="output_pydantic_validator",
                        decision=Decision.FALLBACK,
                        mode=out_mode,
                        score_band=ScoreBand.MEDIUM,
                        categories=["invalid_output_schema"],
                        latency_ms=0.0,
                        degraded=False,
                    )
                )

        out_verdict = self.decision_engine.evaluate(
            request_id=req_id,
            layer="output",
            mode=out_mode,
            results=out_results,
            policy_version=self.settings.GUARDRAILS_POLICY_VERSION,
            guardrails_enabled=self.settings.GUARDRAILS_ENABLED,
        )
        pii_verdict = self.decision_engine.evaluate(
            request_id=req_id,
            layer="pii",
            mode=pii_mode,
            results=pii_results,
            policy_version=self.settings.GUARDRAILS_POLICY_VERSION,
            guardrails_enabled=self.settings.GUARDRAILS_ENABLED,
        )

        all_results = out_verdict.layer_results + pii_verdict.layer_results
        await self._emit_security_events(
            request_id=req_id,
            user_id=user_id,
            raw_message=assistant_text,
            results=all_results,
            db=db,
        )

        wall_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        if out_verdict.effective_decision in (Decision.BLOCK, Decision.FALLBACK, Decision.REQUIRE_REVIEW):
            return out_verdict.model_copy(
                update={
                    "effective_decision": Decision.FALLBACK,
                    "latency_ms": wall_ms,
                    "layer_results": all_results,
                    "degraded": out_verdict.degraded or pii_verdict.degraded,
                }
            )
        if pii_verdict.effective_decision == Decision.REDACT:
            return GuardrailVerdict(
                request_id=req_id,
                layer="output",
                mode=pii_mode,
                effective_decision=Decision.REDACT,
                raw_decision=pii_verdict.raw_decision,
                policy_version=self.settings.GUARDRAILS_POLICY_VERSION,
                latency_ms=wall_ms,
                user_safe_message=None,
                redacted_content=pii_verdict.redacted_content or assistant_text,
                reason_category=pii_verdict.reason_category or "pii_redacted",
                layer_results=all_results,
                degraded=out_verdict.degraded or pii_verdict.degraded,
            )

        raw_dec = out_verdict.raw_decision if out_verdict.raw_decision != Decision.ALLOW else pii_verdict.raw_decision
        return GuardrailVerdict(
            request_id=req_id,
            layer="output",
            mode=out_mode,
            effective_decision=Decision.ALLOW,
            raw_decision=raw_dec,
            policy_version=self.settings.GUARDRAILS_POLICY_VERSION,
            latency_ms=wall_ms,
            user_safe_message=None,
            redacted_content=assistant_text,
            reason_category=None,
            layer_results=all_results,
            degraded=out_verdict.degraded or pii_verdict.degraded,
        )

    async def check_cache_hit_output(
        self,
        assistant_text: str,
        *,
        request_id: str | None = None,
        user_id: str | uuid.UUID | None = None,
        db: AsyncSession | None = None,
    ) -> GuardrailVerdict:
        """Cheap secret/canary scan only for cache hits."""
        t0 = time.perf_counter()
        req_id = request_id or uuid.uuid4().hex
        out_mode = LayerMode(self.settings.get_layer_mode("output"))
        if not self.settings.GUARDRAILS_ENABLED or out_mode == LayerMode.OFF:
            return GuardrailVerdict(
                request_id=req_id,
                layer="output",
                mode=out_mode,
                effective_decision=Decision.ALLOW,
                raw_decision=Decision.ALLOW,
                policy_version=self.settings.GUARDRAILS_POLICY_VERSION,
                latency_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                redacted_content=assistant_text,
                layer_results=[],
            )
        sec_res = await self.secret_scanner_detector.check(assistant_text, layer="output", mode=out_mode)
        verdict = self.decision_engine.evaluate(
            request_id=req_id,
            layer="output",
            mode=out_mode,
            results=[sec_res],
            policy_version=self.settings.GUARDRAILS_POLICY_VERSION,
            guardrails_enabled=self.settings.GUARDRAILS_ENABLED,
        )
        await self._emit_security_events(
            request_id=req_id,
            user_id=user_id,
            raw_message=assistant_text,
            results=verdict.layer_results,
            db=db,
        )
        if verdict.effective_decision in (Decision.BLOCK, Decision.FALLBACK, Decision.REQUIRE_REVIEW):
            return verdict.model_copy(update={"effective_decision": Decision.FALLBACK})
        return verdict.model_copy(update={"redacted_content": assistant_text})


_service_instance: GuardrailsService | None = None


def get_guardrails_service(settings: GuardrailsSettings | None = None) -> GuardrailsService:
    """Return or initialize the singleton GuardrailsService."""
    global _service_instance
    if settings is not None:
        _service_instance = GuardrailsService(settings=settings)
        return _service_instance
    if _service_instance is None:
        _service_instance = GuardrailsService()
    return _service_instance
