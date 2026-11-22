"""Step 2 unit tests: decision engine, config validation, pybreaker circuit breakers, and zero-raw-text events."""

import ast
import asyncio
import json
import pathlib
import uuid

import pybreaker
import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
from app.guardrails.config.settings import GuardrailsSettings
from app.guardrails.decision_engine import DecisionEngine
from app.guardrails.events import (
    GuardrailEvent,
    build_security_event,
    compute_keyed_hash,
    log_security_event,
    serialize_security_event_json,
    write_security_event,
)
from app.guardrails.lifecycle import DetectorCircuitBreaker, GuardrailsLifecycleManager
from app.guardrails.schemas import (
    Decision,
    GuardrailVerdict,
    LayerMode,
    LayerResult,
    ScoreBand,
    SecurityEvent,
)
from app.guardrails.service import GuardrailsService


# ---------------------------------------------------------------------------
# 1. Config Validation Tests
# ---------------------------------------------------------------------------


def test_default_settings_every_layer_is_shadow() -> None:
    settings = GuardrailsSettings()
    assert settings.GUARDRAILS_ENABLED is True
    assert settings.GUARDRAILS_INPUT_MODE == "shadow"
    assert settings.GUARDRAILS_PII_MODE == "shadow"
    assert settings.GUARDRAILS_OUTPUT_MODE == "shadow"
    assert settings.GUARDRAILS_CACHE_MODE == "shadow"
    assert settings.GUARDRAILS_TOOL_MODE == "shadow"
    for layer in ("input", "pii", "output", "cache", "tool"):
        assert settings.get_layer_mode(layer) == "shadow"


@pytest.mark.parametrize(
    "invalid_kwargs",
    [
        {"GUARDRAILS_POLICY_VERSION": "invalid-version"},
        {"GUARDRAILS_POLICY_VERSION": ""},
        {"GUARDRAILS_INPUT_MODE": "block_all"},
        {"GUARDRAILS_PII_MODE": "invalid"},
        {"GUARDRAILS_OUTPUT_MODE": "enabled"},
        {"GUARDRAILS_SELF_CHECK_TIMEOUT_SEC": 0.0},
        {"GUARDRAILS_CONTENT_SAFETY_TIMEOUT_SEC": -1.5},
        {"GUARDRAILS_PII_TIMEOUT_SEC": 45.0},
        {"GUARDRAILS_SELF_CHECK_MODEL_ID": "invalid_model_without_slash"},
        {"GUARDRAILS_CONTENT_SAFETY_MODEL_ID": "nvidia/llama-3.1-nemoguard-8b-content-safety"},
        {"GUARDRAILS_CONTENT_SAFETY_MODEL_ID": "nvidia/nemotron-content-safety-reasoning-4b"},
        {"GUARDRAILS_CONTENT_SAFETY_MODEL_ID": "meta/llama-guard-4-12b"},
        {"GUARDRAILS_SPACY_MODEL_NAME": "en_core_web_lg"},
        {"GUARDRAILS_HASH_KEY": "short_key"},
        {"GUARDRAILS_CB_FAIL_MAX": 0},
        {"GUARDRAILS_CB_RESET_TIMEOUT_SEC": 0},
        {"GUARDRAILS_MAX_INPUT_CHARS": 0},
    ],
)
def test_bad_config_fails_at_startup(invalid_kwargs: dict) -> None:
    with pytest.raises(ValidationError):
        GuardrailsSettings(**invalid_kwargs)


# ---------------------------------------------------------------------------
# 2. Decision Engine Outcome Tests Across Modes & Policy Rules
# ---------------------------------------------------------------------------


def test_decision_engine_modes_off_shadow_enforce() -> None:
    engine = DecisionEngine()
    attack_result = LayerResult(
        layer="input",
        detector="self_check_input",
        decision=Decision.BLOCK,
        mode=LayerMode.SHADOW,
        score_band=ScoreBand.HIGH,
        categories=["prompt_injection"],
        latency_ms=120.5,
    )

    # OFF mode -> raw ALLOW, effective ALLOW
    verdict_off = engine.evaluate(
        request_id="req-off-1",
        layer="input",
        mode=LayerMode.OFF,
        results=[attack_result],
        policy_version="v1.0",
    )
    assert verdict_off.raw_decision == Decision.ALLOW
    assert verdict_off.effective_decision == Decision.ALLOW
    assert verdict_off.user_safe_message is None

    # SHADOW mode -> raw FALLBACK (recorded for audit), effective ALLOW (traffic passes)
    verdict_shadow = engine.evaluate(
        request_id="req-shadow-1",
        layer="input",
        mode=LayerMode.SHADOW,
        results=[attack_result],
        policy_version="v1.0",
    )
    assert verdict_shadow.raw_decision == Decision.FALLBACK
    assert verdict_shadow.effective_decision == Decision.ALLOW
    assert verdict_shadow.user_safe_message is None

    # ENFORCE mode -> either input detector fires -> FALLBACK
    verdict_enforce = engine.evaluate(
        request_id="req-enforce-1",
        layer="input",
        mode=LayerMode.ENFORCE,
        results=[
            attack_result.model_copy(update={"mode": LayerMode.ENFORCE}),
            LayerResult(
                layer="input",
                detector="content_safety_input",
                decision=Decision.ALLOW,
                mode=LayerMode.ENFORCE,
                score_band=ScoreBand.LOW,
                latency_ms=95.0,
            ),
        ],
        policy_version="v1.0",
    )
    assert verdict_enforce.raw_decision == Decision.FALLBACK
    assert verdict_enforce.effective_decision == Decision.FALLBACK
    assert verdict_enforce.user_safe_message is not None
    assert "req-enforce-1" in verdict_enforce.user_safe_message
    assert "self_check_input" not in verdict_enforce.user_safe_message
    assert "prompt_injection" not in verdict_enforce.user_safe_message


def test_decision_engine_one_detector_unavailable_vs_both_unavailable() -> None:
    engine = DecisionEngine()

    # One unavailable, one healthy ALLOW -> ALLOW + degraded=True
    verdict_one_down_allow = engine.evaluate(
        request_id="req-deg-1",
        layer="input",
        mode=LayerMode.ENFORCE,
        results=[
            LayerResult(
                layer="input",
                detector="self_check_input",
                decision=Decision.FALLBACK,
                mode=LayerMode.ENFORCE,
                score_band=ScoreBand.UNAVAILABLE,
                degraded=True,
                error_code="timeout",
                latency_ms=4000.0,
            ),
            LayerResult(
                layer="input",
                detector="content_safety_input",
                decision=Decision.ALLOW,
                mode=LayerMode.ENFORCE,
                score_band=ScoreBand.LOW,
                degraded=False,
                latency_ms=210.0,
            ),
        ],
        policy_version="v1.0",
    )
    assert verdict_one_down_allow.degraded is True
    assert verdict_one_down_allow.raw_decision == Decision.ALLOW
    assert verdict_one_down_allow.effective_decision == Decision.ALLOW

    # Both unavailable -> FALLBACK + degraded=True
    verdict_both_down = engine.evaluate(
        request_id="req-deg-2",
        layer="input",
        mode=LayerMode.ENFORCE,
        results=[
            LayerResult(
                layer="input",
                detector="self_check_input",
                decision=Decision.FALLBACK,
                mode=LayerMode.ENFORCE,
                score_band=ScoreBand.UNAVAILABLE,
                degraded=True,
                error_code="timeout",
                latency_ms=4000.0,
            ),
            LayerResult(
                layer="input",
                detector="content_safety_input",
                decision=Decision.FALLBACK,
                mode=LayerMode.ENFORCE,
                score_band=ScoreBand.UNAVAILABLE,
                degraded=True,
                error_code="circuit_open",
                latency_ms=1.0,
            ),
        ],
        policy_version="v1.0",
    )
    assert verdict_both_down.degraded is True
    assert verdict_both_down.raw_decision == Decision.FALLBACK
    assert verdict_both_down.effective_decision == Decision.FALLBACK


def test_decision_engine_privacy_categories_never_block_and_self_harm_is_supportive() -> None:
    engine = DecisionEngine()

    # Privacy/PII category from content safety never maps to BLOCK/FALLBACK
    verdict_pii_no_redact = engine.evaluate(
        request_id="req-pii-1",
        layer="input",
        mode=LayerMode.ENFORCE,
        results=[
            LayerResult(
                layer="input",
                detector="content_safety_input",
                decision=Decision.BLOCK,
                mode=LayerMode.ENFORCE,
                score_band=ScoreBand.MEDIUM,
                categories=["PII", "privacy"],
                latency_ms=300.0,
            )
        ],
        policy_version="v1.0",
    )
    assert verdict_pii_no_redact.effective_decision == Decision.ALLOW

    verdict_pii_with_redact = engine.evaluate(
        request_id="req-pii-2",
        layer="pii",
        mode=LayerMode.ENFORCE,
        results=[
            LayerResult(
                layer="pii",
                detector="presidio_pii",
                decision=Decision.BLOCK,
                mode=LayerMode.ENFORCE,
                score_band=ScoreBand.MEDIUM,
                categories=["PII"],
                redacted_text="My email is <EMAIL_ADDRESS>",
                latency_ms=35.0,
            )
        ],
        policy_version="v1.0",
    )
    assert verdict_pii_with_redact.effective_decision == Decision.REDACT
    assert verdict_pii_with_redact.redacted_content == "My email is <EMAIL_ADDRESS>"

    # Self-harm category produces supportive crisis helpline message
    verdict_self_harm = engine.evaluate(
        request_id="req-sh-1",
        layer="input",
        mode=LayerMode.ENFORCE,
        results=[
            LayerResult(
                layer="input",
                detector="content_safety_input",
                decision=Decision.BLOCK,
                mode=LayerMode.ENFORCE,
                score_band=ScoreBand.CRITICAL,
                categories=["Suicide and Self Harm"],
                latency_ms=410.0,
            )
        ],
        policy_version="v1.0",
    )
    assert verdict_self_harm.effective_decision == Decision.FALLBACK
    assert verdict_self_harm.user_safe_message is not None
    assert "Tele-MANAS" in verdict_self_harm.user_safe_message
    assert "988" in verdict_self_harm.user_safe_message
    assert "req-sh-1" in verdict_self_harm.user_safe_message


# ---------------------------------------------------------------------------
# 3. Circuit Breaker (pybreaker) Open / Half-Open / Close Tests
# ---------------------------------------------------------------------------


def test_circuit_breaker_closed_open_half_open_closed_transitions() -> None:
    async def _run() -> None:
        cb = DetectorCircuitBreaker(
            name="test_detector",
            fail_max=2,
            reset_timeout=1,
            timeout_sec=0.2,
        )
        assert cb.current_state == "closed"

        async def failing_call() -> str:
            raise RuntimeError("detector upstream 503")

        async def succeeding_call() -> str:
            return "ok"

        # Failure 1 -> still closed (fail_counter = 1)
        with pytest.raises(RuntimeError):
            await cb.call_async(failing_call)
        assert cb.current_state == "closed"
        assert cb.fail_counter == 1

        # Failure 2 -> trips breaker to open (fail_max = 2 reached)
        with pytest.raises(pybreaker.CircuitBreakerError):
            await cb.call_async(failing_call)
        assert cb.current_state == "open"

        # Subsequent call while open is rejected immediately with CircuitBreakerError
        with pytest.raises(pybreaker.CircuitBreakerError):
            await cb.call_async(succeeding_call)
        assert cb.current_state == "open"

        # Transition to half-open and verify failure in half-open re-opens breaker
        cb.half_open()
        assert cb.current_state == "half-open"
        with pytest.raises(pybreaker.CircuitBreakerError):
            await cb.call_async(failing_call)
        assert cb.current_state == "open"

        # After reset_timeout elapses, next call enters half-open and closes on success
        await asyncio.sleep(1.1)
        result = await cb.call_async(succeeding_call)
        assert result == "ok"
        assert cb.current_state == "closed"
        assert cb.fail_counter == 0

    asyncio.run(_run())


def test_circuit_breaker_timeout_trips_breaker() -> None:
    async def _run() -> None:
        cb = DetectorCircuitBreaker(
            name="timeout_detector",
            fail_max=1,
            reset_timeout=30,
            timeout_sec=0.05,
        )

        async def slow_detector() -> str:
            await asyncio.sleep(0.3)
            return "too_late"

        with pytest.raises(pybreaker.CircuitBreakerError):
            await cb.call_async(slow_detector)
        assert cb.current_state == "open"

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 4. Events Never Contain Raw Text Tests
# ---------------------------------------------------------------------------


def test_security_event_never_contains_raw_text_in_schema_logs_or_db() -> None:
    async def _run() -> None:
        raw_secret_prompt = "SECRET_PROMPT_My_Aadhaar_is_4921_8374_6152_and_email_is_alice@example.com"
        raw_user_id = "user-uuid-99887766"
        hash_key = "unit_test_hmac_secret_key_min_16_chars"

        # 1. Verify SQLAlchemy table columns contain no raw text columns
        col_names = set(GuardrailEvent.__table__.columns.keys())
        forbidden_cols = {"query", "prompt", "message", "text", "content", "response", "raw_text", "user_id"}
        assert col_names.isdisjoint(forbidden_cols)

        # 2. Verify SecurityEvent schema forbids extra/raw-text fields
        with pytest.raises(ValidationError):
            SecurityEvent(
                request_id="req-1",
                user_id_hash=compute_keyed_hash(raw_user_id, hash_key),
                layer="input",
                decision=Decision.FALLBACK,
                score_band="high",
                detector="self_check_input",
                latency_ms=12.3,
                policy_version="v1.0",
                mode="shadow",
                message_hash=compute_keyed_hash(raw_secret_prompt, hash_key),
                message_length=len(raw_secret_prompt),
                raw_text=raw_secret_prompt,  # type: ignore[call-arg]
            )

        # 3. Verify build_security_event, JSON log serialization, and SQLite DB write
        event = build_security_event(
            request_id="req-audit-100",
            user_id=raw_user_id,
            layer="input",
            decision=Decision.FALLBACK,
            score_band=ScoreBand.HIGH,
            detector="self_check_input",
            latency_ms=45.67,
            policy_version="v1.0",
            mode="shadow",
            raw_message=raw_secret_prompt,
            hash_key=hash_key,
        )

        json_line = log_security_event(event)
        assert raw_secret_prompt not in json_line
        assert "4921_8374_6152" not in json_line
        assert "alice@example.com" not in json_line
        assert raw_user_id not in json_line
        assert hash_key not in json_line

        parsed = json.loads(json_line)
        assert parsed["message_length"] == len(raw_secret_prompt)
        assert len(parsed["message_hash"]) == 64
        assert len(parsed["user_id_hash"]) == 64

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, tables=[GuardrailEvent.__table__])

        session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_maker() as session:
            db_row = await write_security_event(session, event)
            await session.commit()
            assert db_row.request_id == "req-audit-100"
            assert db_row.message_length == len(raw_secret_prompt)
            assert db_row.message_hash == event.message_hash
            assert db_row.user_id_hash == event.user_id_hash

        await engine.dispose()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 5. GuardrailsService Stub & Module Isolation Tests
# ---------------------------------------------------------------------------


def test_guardrails_service_stub_returns_allow_and_modules_are_isolated() -> None:
    async def _run() -> None:
        settings = GuardrailsSettings()
        lifecycle = GuardrailsLifecycleManager(settings=settings)
        service = GuardrailsService(settings=settings, lifecycle=lifecycle)
        await service.startup()
        assert service.health_snapshot()["initialized"] is True

        # In default shadow mode, effective_decision is always ALLOW even before self-tests run
        in_verdict: GuardrailVerdict = await service.check_input("Hello world", request_id="req-stub-1")
        assert in_verdict.effective_decision == Decision.ALLOW
        assert in_verdict.mode == LayerMode.SHADOW

        out_verdict: GuardrailVerdict = await service.check_output("Hello", "Hi there!", request_id="req-stub-2")
        assert out_verdict.effective_decision == Decision.ALLOW
        assert out_verdict.mode == LayerMode.SHADOW

        await service.shutdown()
        assert service.health_snapshot()["initialized"] is False

    asyncio.run(_run())

    # Verify sibling modules (decision_engine, lifecycle, events) never import each other
    guardrails_dir = pathlib.Path(__file__).resolve().parent.parent / "app" / "guardrails"
    sibling_modules = {"decision_engine", "lifecycle", "events"}
    for mod_name in sibling_modules:
        src = (guardrails_dir / f"{mod_name}.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        other_siblings = sibling_modules - {mod_name}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for sibling in other_siblings:
                    assert not node.module.startswith(f"app.guardrails.{sibling}"), (
                        f"{mod_name}.py must not import sibling module {sibling}.py"
                    )
