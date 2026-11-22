"""Presidio privacy detector with en_core_web_sm and structured Indian-ID recognizers.

Only structured entities (IN_AADHAAR with Verhoeff checksum, IN_PAN, IN_PHONE,
PHONE_NUMBER, EMAIL_ADDRESS, and CREDIT_CARD with Luhn checksum) drive REDACT.
PERSON, LOCATION, and NRP are never queried or acted on.
"""

import asyncio
import re
import time
from typing import Any

import pybreaker
from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

from app.guardrails.config.settings import GuardrailsSettings, get_guardrails_settings
from app.guardrails.schemas import Decision, LayerMode, LayerResult, ScoreBand

# Strictly structured PII entities only — never PERSON, LOCATION, or NRP.
ALLOWED_STRUCTURED_ENTITIES: tuple[str, ...] = (
    "IN_AADHAAR",
    "IN_PAN",
    "IN_PHONE",
    "PHONE_NUMBER",
    "EMAIL_ADDRESS",
    "CREDIT_CARD",
)

FORBIDDEN_NER_ENTITIES: frozenset[str] = frozenset({"PERSON", "LOCATION", "NRP"})

# Verhoeff multiplication table (d)
_VERHOEFF_D: tuple[tuple[int, ...], ...] = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)

# Verhoeff permutation table (p)
_VERHOEFF_P: tuple[tuple[int, ...], ...] = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)

# Verhoeff inverse table (inv)
_VERHOEFF_INV: tuple[int, ...] = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)


def verhoeff_validate(number_str: str) -> bool:
    """Return True if `number_str` (after stripping spaces/hyphens) is a valid 12-digit Verhoeff Aadhaar number."""
    digits = re.sub(r"[\s\-]", "", number_str or "")
    if len(digits) != 12 or not digits.isdigit():
        return False
    if digits[0] in ("0", "1"):
        return False
    c = 0
    for i, ch in enumerate(reversed(digits)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[i % 8][int(ch)]]
    return c == 0


def generate_verhoeff_aadhaar(prefix_11: str = "49218374615") -> str:
    """Compute the Verhoeff check digit for an 11-digit prefix and return a formatted 12-digit Aadhaar string."""
    digits = re.sub(r"[\s\-]", "", prefix_11)
    if len(digits) != 11 or not digits.isdigit() or digits[0] in ("0", "1"):
        raise ValueError("prefix_11 must be 11 digits starting with 2..9")
    c = 0
    for i, ch in enumerate(reversed(digits)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[(i + 1) % 8][int(ch)]]
    check_digit = _VERHOEFF_INV[c]
    full = f"{digits}{check_digit}"
    return f"{full[:4]} {full[4:8]} {full[8:12]}"


class AadhaarVerhoeffRecognizer(PatternRecognizer):
    """Custom Presidio recognizer for Indian Aadhaar numbers with Verhoeff checksum validation."""

    def __init__(self) -> None:
        patterns = [
            Pattern(
                name="aadhaar_12_digit",
                regex=r"\b[2-9]\d{3}[\s\-]?\d{4}[\s\-]?\d{4}\b",
                score=0.4,
            )
        ]
        super().__init__(
            supported_entity="IN_AADHAAR",
            name="AadhaarVerhoeffRecognizer",
            patterns=patterns,
            context=["aadhaar", "uidai", "kyc", "aadhar"],
        )

    def validate_result(self, pattern_text: str) -> bool:
        """Enforce Verhoeff checksum; returns False (score -> 0.0) if checksum fails."""
        return verhoeff_validate(pattern_text)


class IndianPanRecognizer(PatternRecognizer):
    """Custom Presidio recognizer for Indian Permanent Account Numbers (PAN)."""

    def __init__(self) -> None:
        patterns = [
            Pattern(
                name="indian_pan_pattern",
                regex=r"\b[A-Z]{5}[0-9]{4}[A-Z]\b",
                score=0.85,
            )
        ]
        super().__init__(
            supported_entity="IN_PAN",
            name="IndianPanRecognizer",
            patterns=patterns,
            context=["pan", "income tax", "tax", "kyc"],
        )


class IndianPhoneRecognizer(PatternRecognizer):
    """Custom Presidio recognizer for Indian 10-digit mobile numbers (+91 / 0 / bare 6-9 start)."""

    def __init__(self) -> None:
        patterns = [
            Pattern(
                name="indian_mobile_pattern",
                regex=r"(?:(?:\+|00)91[\s\-]?(?:\(0\)[\s\-]?)?|\b0)?[6-9]\d{4}[\s\-]?\d{5}\b",
                score=0.75,
            )
        ]
        super().__init__(
            supported_entity="IN_PHONE",
            name="IndianPhoneRecognizer",
            patterns=patterns,
            context=["phone", "mobile", "call", "whatsapp", "contact", "sms"],
        )


class PrivacyDetector:
    """Standalone Presidio detector using en_core_web_sm in a background thread pool."""

    detector_name: str = "presidio_pii"

    def __init__(
        self,
        settings: GuardrailsSettings | None = None,
        breaker: Any | None = None,
    ) -> None:
        self.settings = settings or get_guardrails_settings()
        self._breaker = breaker or pybreaker.CircuitBreaker(
            fail_max=self.settings.GUARDRAILS_CB_FAIL_MAX,
            reset_timeout=self.settings.GUARDRAILS_CB_RESET_TIMEOUT_SEC,
            name=self.detector_name,
        )
        self._analyzer: AnalyzerEngine | None = None
        self._anonymizer: AnonymizerEngine | None = None
        self.available: bool = False
        self.self_test_passed: bool = False
        self.last_error: str | None = None

    def _ensure_engines(self) -> tuple[AnalyzerEngine, AnonymizerEngine]:
        if self._analyzer is None or self._anonymizer is None:
            nlp_config = {
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": self.settings.GUARDRAILS_SPACY_MODEL_NAME}],
            }
            provider = NlpEngineProvider(nlp_configuration=nlp_config)
            nlp_engine = provider.create_engine()
            analyzer = AnalyzerEngine(nlp_engine=nlp_engine, default_score_threshold=0.5)
            analyzer.registry.add_recognizer(AadhaarVerhoeffRecognizer())
            analyzer.registry.add_recognizer(IndianPanRecognizer())
            analyzer.registry.add_recognizer(IndianPhoneRecognizer())
            self._analyzer = analyzer
            self._anonymizer = AnonymizerEngine()
        return self._analyzer, self._anonymizer

    def _analyze_and_redact_sync(self, text: str) -> tuple[list[str], str | None]:
        if not text or not text.strip():
            return [], None
        analyzer, anonymizer = self._ensure_engines()
        raw_results = analyzer.analyze(
            text=text,
            language="en",
            entities=list(ALLOWED_STRUCTURED_ENTITIES),
            score_threshold=0.5,
        )
        # Double-check filter: strictly allow only ALLOWED_STRUCTURED_ENTITIES and never PERSON/LOCATION/NRP
        filtered = [
            r
            for r in raw_results
            if r.entity_type in ALLOWED_STRUCTURED_ENTITIES
            and r.entity_type not in FORBIDDEN_NER_ENTITIES
        ]
        if not filtered:
            return [], None

        redact_targets = [r for r in filtered if r.entity_type in ("IN_AADHAAR", "IN_PAN", "CREDIT_CARD")]
        categories = sorted({r.entity_type for r in filtered})
        if not redact_targets:
            return categories, None

        operators = {
            entity: OperatorConfig("replace", {"new_value": f"<{entity}>"})
            for entity in ("IN_AADHAAR", "IN_PAN", "CREDIT_CARD")
        }
        anonymized = anonymizer.anonymize(
            text=text,
            analyzer_results=redact_targets,
            operators=operators,
        )
        return categories, anonymized.text

    async def _invoke_under_breaker(self, text: str, timeout_sec: float) -> tuple[list[str], str | None]:
        if hasattr(self._breaker, "call_async") and hasattr(self._breaker, "timeout_sec"):
            return await self._breaker.call_async(
                asyncio.to_thread,
                self._analyze_and_redact_sync,
                text,
                timeout_sec=timeout_sec,
            )
        return await asyncio.wait_for(
            asyncio.to_thread(self._breaker.call, self._analyze_and_redact_sync, text),
            timeout=timeout_sec,
        )

    async def check(
        self,
        text: str,
        *,
        layer: str = "pii",
        mode: LayerMode | None = None,
        require_available: bool = True,
    ) -> LayerResult:
        """Scan `text` for structured PII entities and return a typed LayerResult."""
        effective_mode = mode or LayerMode(self.settings.get_layer_mode("pii"))
        t0 = time.perf_counter()

        if require_available and not self.available:
            dt_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            fail_decision = (
                Decision.ALLOW
                if self.settings.GUARDRAILS_PII_FAIL_MODE == "open"
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
            categories, redacted_text = await self._invoke_under_breaker(
                text, self.settings.GUARDRAILS_PII_TIMEOUT_SEC
            )
            dt_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            if categories and redacted_text is not None and redacted_text != text:
                return LayerResult(
                    layer=layer,
                    detector=self.detector_name,
                    decision=Decision.REDACT,
                    mode=effective_mode,
                    score_band=ScoreBand.MEDIUM,
                    categories=categories,
                    latency_ms=dt_ms,
                    redacted_text=redacted_text,
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
                if self.settings.GUARDRAILS_PII_FAIL_MODE == "open"
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
        """Run startup self-test: warm up spaCy/Presidio, then 1 valid PII probe must REDACT and 1 benign PERSON/LOCATION probe must ALLOW."""
        try:
            await asyncio.to_thread(self._ensure_engines)
            valid_aadhaar = generate_verhoeff_aadhaar("49218374615")
            harmful_probe = f"Verify my Aadhaar {valid_aadhaar} and PAN ABCDE1234F."
            benign_probe = "Customer Priya Verma asked how Redis caching works in Mumbai."

            harmful_res = await self.check(harmful_probe, require_available=False)
            benign_res = await self.check(benign_probe, require_available=False)

            if (
                not harmful_res.degraded
                and harmful_res.decision == Decision.REDACT
                and harmful_res.redacted_text is not None
                and "<IN_AADHAAR>" in harmful_res.redacted_text
                and "<IN_PAN>" in harmful_res.redacted_text
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
                f"Self-test mismatch: pii_probe={harmful_res.decision}, benign_probe={benign_res.decision}"
            )
            return False
        except BaseException as exc:
            self.available = False
            self.self_test_passed = False
            self.last_error = f"{type(exc).__name__}"
            return False
