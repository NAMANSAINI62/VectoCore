"""Comprehensive tests for language-aware exact/semantic caching and Redis locking."""

import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.cache import redis_client
from app.chatbot.graph import (
    SYSTEM_PROMPT,
    check_cache,
    generate_response,
    persist_response,
    validate_generated_response_language,
)
from app.services.cache_engine import (
    SemanticCacheEngine,
    compute_exact_cache_key,
    is_context_dependent_followup,
    normalize_query_for_cache,
)
from app.services.response_language_resolver import (
    detect_input_language,
    extract_explicit_override,
    resolve_response_language,
    resolve_response_language_async,
)


# ---------------------------------------------------------------------------
# 1. Language Resolution Tests (15 cases)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "expected_input", "expected_eff", "expected_policy"),
    [
        ("What are the advantages of Python?", "English", "English", "default"),
        ("पायथन प्रोग्रामिंग लैंग्वेज क्या है?", "Hindi", "English", "default"),
        ("Python programming language kya hai aur ye kaise kaam karti hai?", "Hinglish", "English", "default"),
        ("日本語で質問していますが、Pythonとは何ですか？", "Japanese", "English", "default"),
        ("¿Cómo puedo reducir el consumo de memoria?", "Spanish", "English", "default"),
        ("ما هي مميزات لغة بايثون؟", "Arabic", "English", "default"),
        ("Explain the advantages of Python in Hindi.", "English", "Hindi", "explicit_override"),
        ("Explain FastAPI pagination in Hinglish", "English", "Hinglish", "explicit_override"),
        ("Explain Python decorators in Japanese", "English", "Japanese", "explicit_override"),
        ("Explain Redis caching in Spanish please", "English", "Spanish", "explicit_override"),
        ("Explain Docker in English and Hindi", "English", "English + Hindi", "explicit_override"),
        ("What does 'Answer in French' mean?", "English", "English", "default"),
        ("Explain the difference between Hindi and Japanese grammar", "English", "English", "default"),
    ],
)
def test_language_resolution_matrix(query, expected_input, expected_eff, expected_policy):
    res = resolve_response_language(query)
    assert res.input_language == expected_input
    assert res.effective_response_language == expected_eff
    assert res.language_policy == expected_policy


def test_language_resolution_conversation_preference_fallback():
    res = resolve_response_language(
        "What is PostgreSQL indexing?",
        conversation_language_preference="Hindi",
    )
    assert res.effective_response_language == "Hindi"
    assert res.language_policy == "conversation_preference"


def test_language_resolution_explicit_override_beats_conversation_preference():
    res = resolve_response_language(
        "What is PostgreSQL indexing? Answer in Japanese.",
        conversation_language_preference="Hindi",
    )
    assert res.effective_response_language == "Japanese"
    assert res.language_policy == "explicit_override"


# ---------------------------------------------------------------------------
# 2. Exact Cache Tests (10 cases)
# ---------------------------------------------------------------------------


def test_exact_cache_key_determinism_and_scoping():
    uid = uuid.uuid4()
    k1 = compute_exact_cache_key(uid, "openai", "gpt-4o", "what is python", "English")
    k2 = compute_exact_cache_key(uid, "openai", "gpt-4o", "what is python", "English")
    k_hi = compute_exact_cache_key(uid, "openai", "gpt-4o", "what is python", "Hindi")
    k_model = compute_exact_cache_key(uid, "openai", "gpt-4o-mini", "what is python", "English")
    k_user = compute_exact_cache_key(uuid.uuid4(), "openai", "gpt-4o", "what is python", "English")
    k_param = compute_exact_cache_key(uid, "openai", "gpt-4o", "what is python", "English", generation_params="temp=0.2")

    assert k1 == k2
    assert k1 == k_model  # cross-model cache sharing ignores provider/model
    assert len({k1, k_hi, k_model, k_user, k_param}) == 4


@pytest.mark.asyncio
async def test_exact_cache_hit_matching_language():
    uid = uuid.uuid4()
    entry_id = uuid.uuid4()
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=SimpleNamespace(hit_count=0, last_hit_at=None))
    db.commit = AsyncMock()

    payload = json.dumps({
        "entry_id": str(entry_id),
        "response": "Python is a high-level programming language.",
        "response_language": "English",
        "input_tokens": 12,
        "output_tokens": 24,
    })

    with patch("app.services.cache_engine.exact_cache_get", new=AsyncMock(return_value=payload)), \
         patch("app.services.cache_engine.get_embedding_service", return_value=MagicMock()):
        engine = SemanticCacheEngine(db, uid)
        res = await engine.lookup("What is Python?", "openai", "gpt-4o")

    assert res.hit is True
    assert res.cache_type == "exact_hit"
    assert res.cache_source == "Redis Exact Cache"
    assert res.effective_response_language == "English"
    assert res.response == "Python is a high-level programming language."


@pytest.mark.asyncio
async def test_exact_cache_rejects_language_mismatch_and_legacy_entries():
    uid = uuid.uuid4()
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=None)
    db.scalars = AsyncMock(return_value=SimpleNamespace(all=lambda: []))

    legacy_payload = json.dumps({
        "entry_id": str(uuid.uuid4()),
        "response": "Legacy answer",
        "response_language": "en",  # legacy 2-letter code must NOT match "English"
    })
    mismatch_payload = json.dumps({
        "entry_id": str(uuid.uuid4()),
        "response": "यह उत्तर हिंदी में है।",
        "response_language": "Hindi",
    })

    embed_mock = MagicMock()
    embed_mock.embed_query.return_value = [0.1] * 384

    for bad_payload in (legacy_payload, mismatch_payload, json.dumps({"response": "No lang"})):
        with patch("app.services.cache_engine.exact_cache_get", new=AsyncMock(return_value=bad_payload)), \
             patch("app.services.cache_engine.get_embedding_service", return_value=embed_mock):
            engine = SemanticCacheEngine(db, uid)
            res = await engine.lookup("What is Python?", "openai", "gpt-4o")
        assert res.hit is False
        assert res.cache_type == "miss"


@pytest.mark.asyncio
async def test_exact_cache_empty_query_is_miss():
    db = AsyncMock()
    with patch("app.services.cache_engine.get_embedding_service", return_value=MagicMock()):
        engine = SemanticCacheEngine(db, uuid.uuid4())
        res = await engine.lookup("   ...  ", "openai", "gpt-4o")
    assert res.hit is False
    assert res.cache_type == "miss"


@pytest.mark.asyncio
async def test_store_persists_response_language_and_uses_lock():
    uid = uuid.uuid4()
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.scalar = AsyncMock(return_value=None)

    embed_mock = MagicMock()
    embed_mock.embed_query.return_value = [0.25] * 384
    embed_mock.model_name = "test-embed"

    set_mock = AsyncMock(return_value=True)
    lock_acq = AsyncMock(return_value=True)
    lock_rel = AsyncMock(return_value=True)

    with patch("app.services.cache_engine.get_embedding_service", return_value=embed_mock), \
         patch("app.services.cache_engine.exact_cache_set", new=set_mock), \
         patch("app.services.cache_engine.acquire_cache_lock", new=lock_acq), \
         patch("app.services.cache_engine.release_cache_lock", new=lock_rel):
        engine = SemanticCacheEngine(db, uid)
        entry = await engine.store("पायथन क्या है?", "Python is a language.", "openai", "gpt-4o", 10, 20)

    assert entry.detected_language == "English"
    lock_acq.assert_awaited_once()
    lock_rel.assert_awaited_once()
    set_mock.assert_awaited_once()
    stored_json = json.loads(set_mock.call_args.args[1])
    assert stored_json["response_language"] == "English"
    assert stored_json["input_language"] == "Hindi"
    assert stored_json["language_policy"] == "default"


# ---------------------------------------------------------------------------
# 3. Semantic Cache Tests (8 cases)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_semantic_cache_cross_lingual_default_english_hit_without_translation():
    uid = uuid.uuid4()
    candidate = SimpleNamespace(
        id=uuid.uuid4(),
        query="How can I reduce the memory consumption of my application?",
        response="You can profile allocations, stream large payloads, and reuse objects.",
        query_embedding=[1.0, 0.0, 0.0],
        detected_language="English",
        model="gpt-4o",
        input_tokens=15,
        output_tokens=30,
        hit_count=0,
        last_hit_at=None,
    )
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=None)
    db.scalars = AsyncMock(return_value=SimpleNamespace(all=lambda: [candidate]))
    db.commit = AsyncMock()

    embed_mock = MagicMock()
    embed_mock.embed_query.return_value = [0.99, 0.1, 0.0]

    with patch("app.services.cache_engine.exact_cache_get", new=AsyncMock(return_value=None)), \
         patch("app.services.cache_engine.get_embedding_service", return_value=embed_mock), \
         patch(
             "app.services.cache_engine.validate_candidate_intent",
             new=AsyncMock(
                 return_value=SimpleNamespace(
                     is_valid=True,
                     reason="same_intent",
                     confidence=0.95,
                     intent_summary="Memory optimization guidance",
                 )
             ),
         ):
        engine = SemanticCacheEngine(db, uid)
        res = await engine.lookup(
            "Apne application ki memory usage kaise kam kar sakta hoon?",
            "openai",
            "gpt-4o",
        )

    assert res.hit is True
    assert res.cache_type == "semantic_hit"
    assert res.cache_source == "Semantic Cache"
    assert res.effective_response_language == "English"
    assert res.translation_performed is False
    assert candidate.hit_count == 1


@pytest.mark.asyncio
async def test_semantic_cache_blocks_language_mismatch_and_legacy_candidates():
    uid = uuid.uuid4()
    hindi_candidate = SimpleNamespace(
        id=uuid.uuid4(),
        query="How to reduce memory in Hindi?",
        response="मेमोरी कम करने के तरीके...",
        query_embedding=[1.0, 0.0, 0.0],
        detected_language="Hindi",
        model="gpt-4o",
        input_tokens=10,
        output_tokens=20,
        hit_count=0,
    )
    legacy_candidate = SimpleNamespace(
        id=uuid.uuid4(),
        query="Legacy English query",
        response="Legacy text",
        query_embedding=[1.0, 0.0, 0.0],
        detected_language="en",
        model="gpt-4o",
        input_tokens=10,
        output_tokens=20,
        hit_count=0,
    )
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=None)
    db.scalars = AsyncMock(return_value=SimpleNamespace(all=lambda: [hindi_candidate, legacy_candidate]))

    embed_mock = MagicMock()
    embed_mock.embed_query.return_value = [1.0, 0.0, 0.0]

    with patch("app.services.cache_engine.exact_cache_get", new=AsyncMock(return_value=None)), \
         patch("app.services.cache_engine.get_embedding_service", return_value=embed_mock):
        engine = SemanticCacheEngine(db, uid)
        res = await engine.lookup("How can I reduce memory usage?", "openai", "gpt-4o")

    assert res.hit is False
    assert res.cache_type == "miss"


@pytest.mark.asyncio
async def test_semantic_cache_rejects_different_intent_or_low_similarity():
    uid = uuid.uuid4()
    candidate = SimpleNamespace(
        id=uuid.uuid4(),
        query="How do I install Docker on Ubuntu?",
        response="Run apt-get install docker.io",
        query_embedding=[1.0, 0.0, 0.0],
        detected_language="English",
        model="gpt-4o",
        input_tokens=10,
        output_tokens=20,
        hit_count=0,
    )
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=None)
    db.scalars = AsyncMock(return_value=SimpleNamespace(all=lambda: [candidate]))

    embed_mock = MagicMock()
    embed_mock.embed_query.return_value = [0.95, 0.2, 0.0]

    with patch("app.services.cache_engine.exact_cache_get", new=AsyncMock(return_value=None)), \
         patch("app.services.cache_engine.get_embedding_service", return_value=embed_mock), \
         patch(
             "app.services.cache_engine.validate_candidate_intent",
             new=AsyncMock(
                 return_value=SimpleNamespace(
                     is_valid=False,
                     reason="intent_mismatch",
                     confidence=0.12,
                     intent_summary="Install vs uninstall Docker",
                 )
             ),
         ):
        engine = SemanticCacheEngine(db, uid)
        res = await engine.lookup("How do I uninstall Docker from Ubuntu?", "openai", "gpt-4o")

    assert res.hit is False
    assert res.cache_type == "miss"


# ---------------------------------------------------------------------------
# 4. LLM Integration & Response Language Validation Tests
# ---------------------------------------------------------------------------


def test_system_prompt_contains_global_language_policy():
    assert "RESPONSE LANGUAGE POLICY:" in SYSTEM_PROMPT
    assert "{effective_response_language}" in SYSTEM_PROMPT
    assert "Default response language is English." in SYSTEM_PROMPT


def test_validate_generated_response_language():
    assert validate_generated_response_language("Python is widely used for backend services.", "English") is True
    assert validate_generated_response_language("The word 'नमस्ते' means hello in English.", "English") is True
    assert validate_generated_response_language("पायथन एक लोकप्रिय प्रोग्रामिंग भाषा है जिसका उपयोग वेब विकास में होता है।", "English") is False
    assert validate_generated_response_language("Pythonは汎用プログラミング言語です。", "English") is False
    assert validate_generated_response_language("पायथन एक लोकप्रिय प्रोग्रामिंग भाषा है।", "Hindi") is True
    assert validate_generated_response_language("Python is a popular programming language used worldwide.", "Hindi") is False
    assert validate_generated_response_language("Python is great. पायथन बहुत अच्छी है।", "English + Hindi") is True


@pytest.mark.asyncio
async def test_generate_response_retries_once_on_language_violation_and_skips_invalid_cache():
    # Case A: First attempt violates English (returns Hindi), retry succeeds in English
    class _FakePrompt:
        def __init__(self, responses):
            self._responses = responses
            self._idx = 0

        def __or__(self, _other):
            return self

        async def astream(self, _inputs, config=None):
            text = self._responses[self._idx]
            self._idx += 1
            yield text

    prompt_retry_ok = _FakePrompt([
        "पायथन एक लोकप्रिय प्रोग्रामिंग भाषा है जिसका उपयोग डेटा साइंस में होता है।",
        "Python is a popular programming language used in data science.",
    ])

    state_ok = {
        "prompt": prompt_retry_ok,
        "provider": "openai",
        "model": "gpt-4o",
        "history": [],
        "message": "पायथन क्या है?",
        "effective_response_language": "English",
    }

    with patch("app.chatbot.graph.get_chat_model", return_value=MagicMock()), \
         patch("app.chatbot.graph.get_stream_writer", return_value=lambda _evt: None):
        out_ok = await generate_response(state_ok)

    assert out_ok["language_valid"] is True
    assert "Python is a popular programming language" in out_ok["raw_answer"]

    # Case B: Both attempts violate English -> language_valid is False -> persist_response must NOT store in cache
    prompt_retry_fail = _FakePrompt([
        "पायथन एक लोकप्रिय प्रोग्रामिंग भाषा है।",
        "पायथन एक बहुत अच्छी प्रोग्रामिंग भाषा है।",
    ])
    state_fail = {**state_ok, "prompt": prompt_retry_fail}
    with patch("app.chatbot.graph.get_chat_model", return_value=MagicMock()), \
         patch("app.chatbot.graph.get_stream_writer", return_value=lambda _evt: None):
        out_fail = await generate_response(state_fail)

    assert out_fail["language_valid"] is False

    # Verify persist_response skips engine.store when language_valid is False
    db = AsyncMock()
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    db.scalar = AsyncMock(return_value=SimpleNamespace(updated_at=None))
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, "id", uuid.uuid4()))

    store_mock = AsyncMock()
    telemetry_mock = AsyncMock()
    mock_engine = SimpleNamespace(store=store_mock, record_telemetry=telemetry_mock)

    with patch("app.chatbot.graph.SemanticCacheEngine", return_value=mock_engine):
        await persist_response({
            "db": db,
            "user_id": uuid.uuid4(),
            "conversation_id": uuid.uuid4(),
            "message": "पायथन क्या है?",
            "answer": out_fail["raw_answer"],
            "provider": "openai",
            "model": "gpt-4o",
            "started_at": 0.0,
            "usage": {"input_tokens": 10, "output_tokens": 20},
            "is_cached": False,
            "language_valid": False,
            "effective_response_language": "English",
            "input_language": "Hindi",
            "language_policy": "default",
        })

    store_mock.assert_not_awaited()
    telemetry_mock.assert_awaited_once()


# ---------------------------------------------------------------------------
# 5. Redis Locking Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redis_fallback_and_lock_acquire_release():
    redis_client._local_memory_cache.clear()
    redis_client._local_locks.clear()

    broken_client = MagicMock()
    broken_client.get = AsyncMock(side_effect=RuntimeError("redis down"))
    broken_client.set = AsyncMock(side_effect=RuntimeError("redis down"))
    broken_client.delete = AsyncMock(side_effect=RuntimeError("redis down"))

    with patch("app.cache.redis_client.get_redis_client", return_value=broken_client):
        await redis_client.exact_cache_set("k:test", "v:test", ex_seconds=60)
        assert await redis_client.exact_cache_get("k:test") == "v:test"
        assert await redis_client.exact_cache_get("k:missing") is None

        assert await redis_client.acquire_cache_lock("lock:1", ttl_seconds=10) is True
        assert await redis_client.acquire_cache_lock("lock:1", ttl_seconds=10) is False
        await redis_client.release_cache_lock("lock:1")
        assert await redis_client.acquire_cache_lock("lock:1", ttl_seconds=10) is True


# ---------------------------------------------------------------------------
# 6. Indirect Language Override & Context-Dependent Follow-up Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_indirect_language_override_directives():
    async def _fake_structured_call(payload):
        q = payload["query"] if isinstance(payload, dict) and "query" in payload else str(payload)
        if "Tokyo" in q and "Reply in" in q:
            return {"has_override": True, "target_language": "Japanese"}
        if "France" in q and "in the national language" in q:
            return {"has_override": True, "target_language": "French"}
        return {"has_override": False, "target_language": None}

    fake_llm = MagicMock()
    fake_llm.with_structured_output.return_value = SimpleNamespace(ainvoke=_fake_structured_call)

    with patch(
        "app.services.response_language_resolver.available_models",
        return_value=[SimpleNamespace(provider="openai", id="gpt-4o-mini")],
    ), patch("app.services.response_language_resolver.get_chat_model", return_value=fake_llm):
        r_tokyo = await resolve_response_language_async("Explain microservices. Reply in the language spoken in Tokyo.")
        assert r_tokyo.effective_response_language == "Japanese"
        assert r_tokyo.language_policy == "explicit_override"

        r_paris = await resolve_response_language_async("Explain Docker in the national language of France.")
        assert r_paris.effective_response_language == "French"
        assert r_paris.language_policy == "explicit_override"

        # Question ABOUT Tokyo's language (no output directive) must stay English!
        r_fact = await resolve_response_language_async("What language is spoken in Tokyo?")
        assert r_fact.effective_response_language == "English"
        assert r_fact.language_policy == "default"


def test_is_context_dependent_followup():
    assert is_context_dependent_followup("Explain step 2") is True
    assert is_context_dependent_followup("Give an example of that") is True
    assert is_context_dependent_followup("Iska example do") is True
    assert is_context_dependent_followup("Why?") is True
    assert is_context_dependent_followup("What is PostgreSQL MVCC?") is False
    assert is_context_dependent_followup("How do I configure Redis persistence?") is False


@pytest.mark.asyncio
async def test_check_cache_bypasses_context_dependent_followup_when_history_exists():
    db = AsyncMock()
    db.bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    db.scalar = AsyncMock(return_value=uuid.uuid4())  # prior completed message exists
    db.scalars = AsyncMock(return_value=SimpleNamespace(all=lambda: []))

    with patch("app.chatbot.graph.get_stream_writer", return_value=lambda _evt: None), \
         patch("app.chatbot.graph.SemanticCacheEngine") as engine_cls:
        out = await check_cache({
            "db": db,
            "user_id": uuid.uuid4(),
            "conversation_id": uuid.uuid4(),
            "user_message_id": uuid.uuid4(),
            "message": "Iska example do",
            "provider": "openrouter",
            "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
        })

    assert out["is_cached"] is False
    assert out["skip_cache"] is True
    engine_cls.assert_not_called()
