"""Automated tests for exact cache behavior and token counting."""

import sys
import uuid
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.v1.endpoints.cache import _compute_percentiles
from app.models.cache import CacheTelemetry
from app.services.cache_engine import compute_exact_cache_key, normalize_query_for_cache
from app.services.token_service import count_tokens


def test_input_output_token_counting():
    assert count_tokens("") == 0
    assert count_tokens("Hello world from the exact cache") >= 5


def test_exact_cache_key_determinism():
    owner_id = uuid.uuid4()
    normalized_a = normalize_query_for_cache("What are the advantages of Python?")
    normalized_b = normalize_query_for_cache("  what are the advantages of python?! ")
    key_a = compute_exact_cache_key(
        owner_id,
        "groq",
        "openai/gpt-oss-20b",
        normalized_a,
    )
    key_b = compute_exact_cache_key(
        owner_id,
        "groq",
        "openai/gpt-oss-20b",
        normalized_b,
    )
    assert normalized_a == normalized_b
    assert key_a == key_b


def test_p50_p95_p99_percentiles():
    p50, p95, p99 = _compute_percentiles([1, 2, 3, 4, 5, 10, 20, 50, 100, 200])
    assert p50 > 0 and p95 >= p50 and p99 >= p95


def test_phase2_libraries_lingua_tiktoken_registry_judge_and_ttlcache():
    import asyncio
    from unittest.mock import patch
    from cachetools import TTLCache
    from app.cache import redis_client
    from app.services.language_service import detect_input_language
    from app.services.intent_service import _resolve_judge_model

    # 1. lingua-py multilingual detection + Hinglish guard
    assert detect_input_language("Explain microservices architecture clearly") == "English"
    assert detect_input_language("पायथन प्रोग्रामिंग क्या है?") == "Hindi"
    assert detect_input_language("Python programming kaise kaam karti hai?") == "Hinglish"
    assert detect_input_language("¿Cómo funciona el almacenamiento en caché?") == "Spanish"
    assert detect_input_language("キャッシュとは何ですか？") == "Japanese"
    assert detect_input_language("ما هي فوائد لغة بايثون؟") == "Arabic"

    # 2. tiktoken accurate counting
    assert count_tokens("") == 0
    assert count_tokens("Hello, semantic caching world!") >= 5

    # 3. Registry-driven judge resolution (no hardcoded provider chains)
    from types import SimpleNamespace
    with patch(
        "app.services.intent_service.available_models",
        return_value=[SimpleNamespace(provider="openrouter", id="qwen/qwen3-32b")],
    ):
        prov, mod = _resolve_judge_model("groq", "openai/gpt-oss-120b")
        assert (prov, mod) == ("openrouter", "qwen/qwen3-32b")

    # 4. Bounded cachetools.TTLCache fallback + local lock lifecycle
    assert isinstance(redis_client._local_memory_cache, TTLCache)
    assert isinstance(redis_client._local_locks, TTLCache)

    async def _exercise_fallback():
        prev_fail = redis_client._last_redis_failure
        redis_client._last_redis_failure = 1e18
        try:
            key = f"llm:exact:test:{uuid.uuid4().hex}"
            await redis_client.exact_cache_set(key, "cached-val", ex_seconds=60)
            assert await redis_client.exact_cache_get(key) == "cached-val"
            assert await redis_client.acquire_cache_lock("lock-test", ttl_seconds=5) is True
            assert await redis_client.acquire_cache_lock("lock-test", ttl_seconds=5) is False
            await redis_client.release_cache_lock("lock-test")
            assert await redis_client.acquire_cache_lock("lock-test", ttl_seconds=5) is True
            await redis_client.release_cache_lock("lock-test")
        finally:
            redis_client._last_redis_failure = prev_fail

    asyncio.run(_exercise_fallback())


def test_hinglish_pivot_parser_fallback():
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.services.intent_service import canonicalize_hinglish_query_for_search

    class _FakeLLM:
        def bind(self, **_kwargs):
            return self

        def with_structured_output(self, _schema):
            return SimpleNamespace(ainvoke=AsyncMock(side_effect=RuntimeError("no structured tool support")))

        async def ainvoke(self, _messages):
            return SimpleNamespace(content='{"english_query": "What is the meaning of Python?"}')

    with patch(
        "app.services.intent_service.available_models",
        return_value=[SimpleNamespace(provider="groq", id="openai/gpt-oss-20b")],
    ), patch("app.services.intent_service.get_chat_model", return_value=_FakeLLM()):
        out = asyncio.run(
            canonicalize_hinglish_query_for_search(
                "Python ka meaning kya hai?",
                provider="groq",
                model="openai/gpt-oss-120b",
            )
        )
    assert out == "What is the meaning of Python?"


def test_qa_fixes_and_cloud_url_normalization(monkeypatch):
    from types import SimpleNamespace
    from app.cache import redis_client
    from app.config.settings import Settings
    from app.services.intent_service import _supports_structured_output
    from app.services.language_service import detect_input_language

    # 1. Mixed English + Devanagari query must detect Hindi (never Esperanto)
    assert detect_input_language("PostgreSQL MVCC क्या है?") == "Hindi"

    # 2. gpt-oss models skip unsupported with_structured_output preflight; standard models keep it
    assert _supports_structured_output(SimpleNamespace(model_name="openai/gpt-oss-20b")) is False
    assert _supports_structured_output(SimpleNamespace(model_name="llama-3.3-70b-versatile")) is True

    # 3. Cloud Postgres URL normalizer (Neon/Supabase/Render) adapts driver & ssl params for asyncpg
    cloud_settings = Settings(
        DATABASE_URL="postgres://u:p@ep-demo.aws.neon.tech/neondb?sslmode=require&channel_binding=require",
        CORS_ORIGINS="https://app.example.com/, http://localhost:3000",
    )
    assert cloud_settings.DATABASE_URL == "postgresql+asyncpg://u:p@ep-demo.aws.neon.tech/neondb?ssl=require"
    assert cloud_settings.CORS_ORIGINS == ["https://app.example.com", "http://localhost:3000"]

    # 4. Remote Redis Cloud URLs widen WAN operation deadline cleanly
    monkeypatch.setattr(
        redis_client,
        "settings",
        Settings(REDIS_URL="rediss://default:secret@redis-12345.c1.us-east-1-2.ec2.cloud.redislabs.com:12345", REDIS_SOCKET_TIMEOUT=2.5),
    )
    assert redis_client._op_timeout(0.25) == 2.5
    monkeypatch.setattr(redis_client, "settings", Settings(REDIS_URL="redis://127.0.0.1:6379/0"))
    assert redis_client._op_timeout(0.25) == 0.25
