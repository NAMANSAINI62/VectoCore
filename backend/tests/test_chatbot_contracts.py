"""Focused tests for provider selection and chatbot request validation."""

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.llm import registry
from app.schemas.chatbot import ChatCompletionRequest
from app.api.v1.endpoints import chatbot as chatbot_endpoint
from app.api.v1.endpoints.chatbot import _owned_conversation, _provider_error, _provider_status_code
from app.chatbot import graph as chatbot_graph
from app.database.base import Base
from app.guardrails.events import GuardrailEvent  # noqa: F401 - register guardrail_events in Base.metadata
from app.models.chat import ChatConversation, ChatMessage
from app.models.user import User


def test_groq_model_is_listed_with_expected_provider() -> None:
    groq_models = [item.id for item in registry.available_models() if item.provider == "groq"]
    assert groq_models == ["openai/gpt-oss-20b", "openai/gpt-oss-120b"]
    assert "llama-3.1-8b-instant" not in groq_models


def test_invalid_provider_model_pair_is_rejected() -> None:
    with pytest.raises(HTTPException) as error:
        registry.validate_provider_model("groq", "not-a-configured-model")
    assert error.value.status_code == 422


def test_valid_model_without_backend_key_reports_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry.settings, "GROQ_API_KEY", "")
    with pytest.raises(HTTPException) as error:
        registry.validate_provider_model("groq", "openai/gpt-oss-20b")
    assert error.value.status_code == 503
    assert "not configured" in error.value.detail


def test_chat_request_trims_message_and_rejects_whitespace() -> None:
    request = ChatCompletionRequest(message="  hello  ")
    assert request.message == "hello"
    with pytest.raises(ValueError):
        ChatCompletionRequest(message="   ")


def test_chat_request_enforces_message_size() -> None:
    with pytest.raises(ValueError):
        ChatCompletionRequest(message="x" * 12001)


def test_provider_errors_are_classified_without_exposing_upstream_details() -> None:
    error_type = type("RateLimitError", (Exception,), {})
    code, detail = _provider_error(error_type())
    assert code == 429
    assert "rate-limited" in detail


def test_provider_http_status_is_preserved_for_sdk_status_errors() -> None:
    error = RuntimeError("upstream response body must not be exposed")
    error.status_code = 429  # type: ignore[attr-defined]

    assert _provider_status_code(error) == 429
    status_code, detail = _provider_error(error)
    assert status_code == 429
    assert "upstream response body" not in detail


def test_provider_http_status_is_read_from_nested_http_response() -> None:
    error = RuntimeError("provider request failed")
    error.response = SimpleNamespace(status_code=429)  # type: ignore[attr-defined]
    assert _provider_status_code(error) == 429


def test_provider_503_high_demand_error_message() -> None:
    error = RuntimeError("503 UNAVAILABLE: This model is currently experiencing high demand")
    error.status_code = 503  # type: ignore[attr-defined]
    code, detail = _provider_error(error)
    assert code == 503
    assert detail == "This model is currently experiencing high demand, so use different models."


def test_failed_cache_lookup_is_recorded_as_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run_recording() -> None:
        records: list[dict[str, object]] = []

        class SessionContext:
            async def __aenter__(self) -> object:
                return object()

            async def __aexit__(self, *_args: object) -> None:
                return None

        class FakeCacheEngine:
            def __init__(self, _db: object, _owner_id: uuid.UUID) -> None:
                pass

            async def record_telemetry(self, **kwargs: object) -> None:
                records.append(kwargs)

        monkeypatch.setattr(chatbot_endpoint, "async_session_factory", SessionContext)
        monkeypatch.setattr(chatbot_endpoint, "SemanticCacheEngine", FakeCacheEngine)
        await chatbot_endpoint._record_failed_cache_lookup(
            {
                "is_cached": False,
                "cache_lookup": SimpleNamespace(lookup_latency_ms=12, similarity_score=0.8868),
                "input_language": "English",
                "effective_response_language": "English",
            },
            user_id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            query="Test request",
            provider="nvidia",
            model="test-model",
            total_latency_ms=250,
        )

        assert len(records) == 1
        assert records[0]["cache_status"] == "miss"
        assert records[0]["input_tokens"] == 0
        assert records[0]["output_tokens"] == 0
        assert records[0]["similarity_score"] == 0.8868

    asyncio.run(run_recording())


def test_graph_uses_history_and_persists_assistant_message(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run_workflow() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync_connection: Base.metadata.create_all(
                    sync_connection,
                    tables=[User.__table__, ChatConversation.__table__, ChatMessage.__table__, GuardrailEvent.__table__],
                )
            )
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        user_id = uuid.uuid4()
        outsider_id = uuid.uuid4()
        conversation_id = uuid.uuid4()
        captured: list[object] = []
        streamed: list[dict[str, object]] = []

        def fake_model(prompt: object) -> AIMessage:
            captured.extend(prompt.to_messages())
            return AIMessage(content="A streamed test response")

        monkeypatch.setattr(chatbot_graph, "validate_provider_model", lambda *_: None)
        monkeypatch.setattr(chatbot_graph, "get_chat_model", lambda *_args, **_kwargs: RunnableLambda(fake_model))

        async with sessions() as session:
            session.add(User(id=user_id, full_name="Test User", email="chat-test@example.com", password_hash="unused"))
            session.add(User(id=outsider_id, full_name="Other User", email="other-chat-test@example.com", password_hash="unused"))
            session.add(
                ChatConversation(
                    id=conversation_id,
                    owner_id=user_id,
                    title="Chat",
                    selected_provider="groq",
                    selected_model="openai/gpt-oss-20b",
                )
            )
            current_user_message = ChatMessage(
                owner_id=user_id,
                conversation_id=conversation_id,
                role="user",
                content="Current question",
            )
            session.add_all(
                [
                    ChatMessage(owner_id=user_id, conversation_id=conversation_id, role="user", content="Earlier question"),
                    ChatMessage(owner_id=user_id, conversation_id=conversation_id, role="assistant", content="Earlier answer"),
                    current_user_message,
                ]
            )
            await session.commit()
            async for _mode, _part in chatbot_graph.chat_graph.astream(
                {
                    "db": session,
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "user_message_id": current_user_message.id,
                    "message": "Current question",
                    "provider": "groq",
                    "model": "openai/gpt-oss-20b",
                },
                stream_mode=["custom", "values"],
            ):
                if _mode == "custom":
                    streamed.append(_part)
            messages = list((await session.scalars(select(ChatMessage).order_by(ChatMessage.created_at, ChatMessage.id))).all())
            assistant_message = next(item for item in messages if item.content == "A streamed test response")
            assert len(messages) == 4
            assert assistant_message.provider == "groq"
            assert assistant_message.model_id == "openai/gpt-oss-20b"
            assert assistant_message.status == "completed"
            assert any(isinstance(item, HumanMessage) and item.content == "Earlier question" for item in captured)
            assert sum(isinstance(item, HumanMessage) and item.content == "Current question" for item in captured) == 1
            content_events = [item for item in streamed if item.get("event") == "content.delta"]
            status_events = [item for item in streamed if item.get("event") == "status.update"]
            assert content_events == [{"event": "content.delta", "data": "A streamed test response"}]
            assert len(status_events) >= 2
            with pytest.raises(HTTPException) as ownership_error:
                outsider = await session.get(User, outsider_id)
                await _owned_conversation(session, outsider, conversation_id)
            assert ownership_error.value.status_code == 404
        await engine.dispose()

    asyncio.run(run_workflow())


def test_gemini_proactive_and_reactive_model_failover(monkeypatch: pytest.MonkeyPatch):
    from langchain_core.messages import AIMessage
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.runnables import RunnableLambda
    from app.llm import registry

    router = registry.get_quota_router()
    router.reset()

    try:
        # Global <=10 RPM safety cap check across high-RPM policies
        for policy in registry._MODEL_QUOTA_POLICIES.values():
            assert policy.rpm_soft_cap <= 10
        assert registry._MODEL_QUOTA_POLICIES["gemini-3-flash-preview"].rpm_soft_cap == 4

        # 1. Proactive switch at <= 10 RPM soft cap for fast query
        for _ in range(10):
            router.record_request("gemini", "gemini-3.5-flash-lite")

        next_prov, next_mod, reason = registry.select_best_model_candidate(
            "gemini", "gemini-3.5-flash-lite", message="Hi"
        )
        assert next_prov == "gemini"
        assert next_mod == "gemini-3.1-flash-lite"
        assert reason is not None and "RPM" in reason

        # Fill 3.1 too (10 RPM) -> advances to gemini-3.1-flash-lite-preview, then gemini-flash-lite-latest
        for _ in range(10):
            router.record_request("gemini", "gemini-3.1-flash-lite")
        next_prov2, next_mod2, reason2 = registry.select_best_model_candidate(
            "gemini", "gemini-3.5-flash-lite", message="Hi"
        )
        assert (next_prov2, next_mod2) == ("gemini", "gemini-3.1-flash-lite-preview")
        assert reason2 is not None

        for _ in range(10):
            router.record_request("gemini", "gemini-3.1-flash-lite-preview")
        next_prov3, next_mod3, reason3 = registry.select_best_model_candidate(
            "gemini", "gemini-3.5-flash-lite", message="Hi"
        )
        assert (next_prov3, next_mod3) == ("gemini", "gemini-flash-lite-latest")
        assert reason3 is not None

        # 2. Reactive 429 failover inside generate_response
        router.reset()
        attempted: list[str] = []

        def fake_get_chat_model(provider: str, model: str, *, streaming: bool = True):
            attempted.append(f"{provider}:{model}")
            if model == "gemini-3.5-flash-lite":
                def _raise(_inp):
                    raise RuntimeError("429 RESOURCE_EXHAUSTED rate limit exceeded")
                return RunnableLambda(_raise)
            return RunnableLambda(lambda _inp: AIMessage(content="Served by fallback 3.1 Flash-Lite."))

        monkeypatch.setattr(chatbot_graph, "get_chat_model", fake_get_chat_model)

        async def _run_reactive():
            monkeypatch.setattr(chatbot_graph, "get_stream_writer", lambda: (lambda _evt: None))
            return await chatbot_graph.generate_response({
                "message": "What is TTL?",
                "provider": "gemini",
                "model": "gemini-3.5-flash-lite",
                "prompt": ChatPromptTemplate.from_messages([("human", "{message}")]),
                "history": [],
                "effective_response_language": "English",
                "input_language": "English",
            })

        result = asyncio.run(_run_reactive())
        assert result["active_provider"] == "gemini"
        assert result["active_model"] == "gemini-3.1-flash-lite"
        assert result["switched_from"] == "3.5 Flash-Lite"
        assert "Served by fallback 3.1 Flash-Lite." in result["raw_answer"]
        assert attempted[:2] == ["gemini:gemini-3.5-flash-lite", "gemini:gemini-3.1-flash-lite"]
    finally:
        router.reset()


def test_gemini_intent_complexity_dynamic_routing():
    from app.config.settings import get_settings
    from app.llm import registry

    router = registry.get_quota_router()
    router.reset()

    try:
        current_settings = get_settings()
        assert current_settings.ACCESS_TOKEN_EXPIRE_MINUTES == 10080

        gemini_opts = [opt for opt in registry.available_models() if opt.provider == "gemini"]
        gemini_ids = {opt.id for opt in gemini_opts}
        assert gemini_ids == {
            "gemma-4-31b-it",
            "gemini-3.8-flash",
            "gemini-3-flash-preview",
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
            "gemini-3.1-flash-lite-preview",
            "gemini-flash-lite-latest",
        }
        # Removed/0-quota/deprecated models stay excluded
        for removed_id in ("gemini-auto", "gemini-4-argon", "gemini-4-carbon", "gemini-2.5-pro", "gemini-2.5-flash", "deep-research-preview-04-2026"):
            assert removed_id not in gemini_ids

        # Every concrete Gemini model belongs to one unique UI tier (no duplicates across tiers)
        tier_buckets = {
            opt.tier: [m.id for m in gemini_opts if m.tier == opt.tier]
            for opt in gemini_opts
            if opt.tier
        }
        assert set(tier_buckets.keys()) == {"deep_research", "complex", "balanced", "fast"}
        all_tiered_ids = [mid for ids in tier_buckets.values() for mid in ids]
        assert len(all_tiered_ids) == len(set(all_tiered_ids))

        # Concrete selection stays on requested model when healthy, then rotates after its soft quota cap.
        prov_dr, mod_dr, reason_dr = registry.select_best_model_candidate(
            "gemini",
            "gemma-4-31b-it",
            message="Perform deep research on distributed semantic cache invalidation.",
        )
        assert (prov_dr, mod_dr) == ("gemini", "gemma-4-31b-it")
        assert reason_dr is None

        for _ in range(25):
            router.record_request("gemini", "gemma-4-31b-it")
        prov_dr2, mod_dr2, _ = registry.select_best_model_candidate(
            "gemini",
            "gemma-4-31b-it",
            message="Perform deep research on distributed semantic cache invalidation.",
        )
        assert (prov_dr2, mod_dr2) == ("gemini", "gemini-3.8-flash")

        # Complex model stays on Gemini 3.8 Flash when healthy, then fails over to Gemini 3 Flash Preview at 4 RPM
        prov_c, mod_c, reason_c = registry.select_best_model_candidate(
            "gemini",
            "gemini-3.8-flash",
            message="Design a distributed architecture step-by-step with tradeoffs.",
        )
        assert (prov_c, mod_c) == ("gemini", "gemini-3.8-flash")
        assert reason_c is None

        for _ in range(4):
            router.record_request("gemini", "gemini-3.8-flash")
        prov_c2, mod_c2, _ = registry.select_best_model_candidate(
            "gemini",
            "gemini-3.8-flash",
            message="Design a distributed architecture step-by-step with tradeoffs.",
        )
        assert (prov_c2, mod_c2) == ("gemini", "gemini-3-flash-preview")

        # Fast short query stays on requested Gemini 3.1 Flash-Lite
        prov_f, mod_f, reason_f = registry.select_best_model_candidate(
            "gemini",
            "gemini-3.1-flash-lite",
            message="What is TTL?",
        )
        assert (prov_f, mod_f) == ("gemini", "gemini-3.1-flash-lite")
        assert reason_f is None

        # Medium balanced query stays on Gemini 3.5 Flash-Lite, then rotates at its soft quota cap.
        prov_b, mod_b, reason_b = registry.select_best_model_candidate(
            "gemini",
            "gemini-3.5-flash-lite",
            message="Compare LRU vs LFU caching policies and show a Python example.",
        )
        assert (prov_b, mod_b) == ("gemini", "gemini-3.5-flash-lite")
        assert reason_b is None

        for _ in range(12):
            router.record_request("gemini", "gemini-3.5-flash-lite")
        prov_b2, mod_b2, _ = registry.select_best_model_candidate(
            "gemini",
            "gemini-3.5-flash-lite",
            message="Compare LRU vs LFU caching policies and show a Python example.",
        )
        assert (prov_b2, mod_b2) == ("gemini", "gemini-3.1-flash-lite")
    finally:
        router.reset()
