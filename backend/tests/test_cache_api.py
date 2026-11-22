"""Tests for Cache Management and Analytics API endpoints."""

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from datetime import datetime, timedelta, timezone
from app.main import app
from app.database.session import async_session_factory
from app.models.user import User
from app.models.cache import CacheEntry, CacheTelemetry
from app.core.security import create_access_token


def test_cache_api_endpoints():
    async def _test():
        user_id = uuid.uuid4()
        session_factory = async_session_factory

        # 1. Create a test user in DB
        async with session_factory() as session:
            user = User(
                id=user_id,
                full_name="Cache API User",
                email=f"cache_api_{user_id.hex[:8]}@example.com",
                password_hash="mock_hash",
            )
            session.add(user)
            await session.commit()

        # Generate JWT token for test user
        token = create_access_token(subject=str(user_id))
        headers = {"Authorization": f"Bearer {token}"}

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            try:
                # 1. GET /api/v1/cache/entries (Initially empty)
                resp = await client.get("/api/v1/cache/entries", headers=headers)
                assert resp.status_code == 200
                data = resp.json()
                assert data["total"] == 0
                assert data["items"] == []

                # 2. Add sample cache entry and telemetry row directly in DB
                entry_id = uuid.uuid4()
                telemetry_id = uuid.uuid4()
                async with session_factory() as session:
                    entry = CacheEntry(
                        id=entry_id,
                        owner_id=user_id,
                        query="What is FastAPI?",
                        normalized_query="what is fastapi",
                        query_embedding=[0.1] * 2048,
                        embedding_dim=2048,
                        embedding_model="test-model",
                        response="FastAPI is a modern Python web framework.",
                        detected_language="en",
                        intent="definition",
                        depth_scope="standard",
                        critical_entities=["fastapi"],
                        provider="groq",
                        model="openai/gpt-oss-120b",
                        config_hash="test_hash_1",
                        input_tokens=12,
                        output_tokens=150,
                        hit_count=3,
                        status="active",
                        expires_at=datetime.now(timezone.utc) + timedelta(days=3),
                    )
                    telemetry = CacheTelemetry(
                        id=telemetry_id,
                        owner_id=user_id,
                        query_preview="What is FastAPI?",
                        current_query="Tell me about FastAPI",
                        matched_entry_id=entry_id,
                        matched_query="What is FastAPI?",
                        matched_queries_snapshot=[
                            {
                                "cache_entry_id": str(entry_id),
                                "previous_query": "What is FastAPI?",
                                "similarity_score": 0.95,
                                "intent_compatible": True,
                                "intent_status": "Compatible",
                                "selected": True,
                            }
                        ],
                        returned_response_snapshot="FastAPI is a modern Python web framework.",
                        validation_explanation="Same core definition intent.",
                        cache_status="semantic_hit",
                        provider="groq",
                        model="openai/gpt-oss-120b",
                        detected_language="en",
                        input_tokens=12,
                        output_tokens=150,
                        total_tokens=162,
                        tokens_saved=162,
                        cache_lookup_latency_ms=15,
                        total_latency_ms=18,
                        similarity_score=0.95,
                    )
                    session.add_all([entry, telemetry])
                    await session.commit()

                # 3. GET /api/v1/cache/entries (Verify listed)
                resp = await client.get("/api/v1/cache/entries", headers=headers)
                assert resp.status_code == 200
                data = resp.json()
                assert data["total"] == 1
                assert len(data["items"]) == 1
                assert data["items"][0]["query"] == "What is FastAPI?"
                assert data["items"][0]["hit_count"] == 3

                # 4. Search filter
                resp = await client.get("/api/v1/cache/entries?search=fastapi", headers=headers)
                assert resp.status_code == 200
                assert resp.json()["total"] == 1

                resp = await client.get("/api/v1/cache/entries?search=nonexistent", headers=headers)
                assert resp.status_code == 200
                assert resp.json()["total"] == 0

                # 5. GET /api/v1/cache/stats
                resp = await client.get("/api/v1/cache/stats", headers=headers)
                assert resp.status_code == 200
                stats = resp.json()
                assert stats["total_requests"] == 1
                assert stats["cache_hits"] == 1
                assert stats["semantic_hits"] == 1
                assert stats["real_tokens_saved"] == 162
                assert stats["hit_rate_pct"] == 100.0
                assert stats["total_entries_count"] == 1
                assert stats["avg_semantic_hit_latency_ms"] == 15.0
                assert stats["avg_overall_latency_ms"] == 18.0
                assert len(stats["daily_trends"]) == 1
                trend = stats["daily_trends"][0]
                assert trend["hit_rate_pct"] == 100.0
                assert trend["input_tokens_saved"] == 12
                assert trend["output_tokens_saved"] == 150
                assert any(b["bucket"] == "10-50ms" and b["semantic_hits"] == 1 for b in stats["latency_buckets"])

                # 5a. GET /api/v1/cache/telemetry/{id}/inspect (semantic_hit vs exact_hit)
                resp = await client.get(f"/api/v1/cache/telemetry/{telemetry_id}/inspect", headers=headers)
                assert resp.status_code == 200
                inspected = resp.json()
                assert inspected["semantic_match_insights"] is not None
                assert inspected["semantic_match_insights"]["current_query"] == "Tell me about FastAPI"
                assert inspected["semantic_match_insights"]["selected_previous_query"] == "What is FastAPI?"
                assert inspected["semantic_match_insights"]["returned_cached_response"] == "FastAPI is a modern Python web framework."
                assert inspected["semantic_match_insights"]["validation_explanation"] == "Same core definition intent."

                exact_telemetry_id = uuid.uuid4()
                async with session_factory() as session:
                    session.add(
                        CacheTelemetry(
                            id=exact_telemetry_id,
                            owner_id=user_id,
                            query_preview="What is FastAPI?",
                            cache_status="exact_hit",
                            provider="groq",
                            model="openai/gpt-oss-120b",
                            detected_language="en",
                            input_tokens=12,
                            output_tokens=150,
                            total_tokens=162,
                            tokens_saved=162,
                            cache_lookup_latency_ms=3,
                            total_latency_ms=5,
                        )
                    )
                    await session.commit()

                resp = await client.get(f"/api/v1/cache/telemetry/{exact_telemetry_id}/inspect", headers=headers)
                assert resp.status_code == 200
                assert resp.json()["semantic_match_insights"] is None

                # 6. GET /api/v1/cache/settings & PATCH /api/v1/cache/settings
                resp = await client.get("/api/v1/cache/settings", headers=headers)
                assert resp.status_code == 200
                assert "similarity_threshold" in resp.json()

                resp = await client.patch(
                    "/api/v1/cache/settings",
                    json={"similarity_threshold": 0.88, "default_ttl_hours": 48},
                    headers=headers,
                )
                assert resp.status_code == 200
                assert resp.json()["similarity_threshold"] == 0.88
                assert resp.json()["default_ttl_hours"] == 48

                # 7. DELETE /api/v1/cache/entries/{id}
                resp = await client.delete(f"/api/v1/cache/entries/{entry_id}", headers=headers)
                assert resp.status_code == 204

                # Verify deleted
                resp = await client.get("/api/v1/cache/entries", headers=headers)
                assert resp.status_code == 200
                assert resp.json()["total"] == 0

            finally:
                # Cleanup
                async with session_factory() as session:
                    await session.execute(delete(CacheTelemetry).where(CacheTelemetry.owner_id == user_id))
                    await session.execute(delete(CacheEntry).where(CacheEntry.owner_id == user_id))
                    await session.execute(delete(User).where(User.id == user_id))
                    await session.commit()
                from app.database.session import engine as db_engine
                await db_engine.dispose()

    asyncio.run(_test())


if __name__ == "__main__":
    test_cache_api_endpoints()
    print("ALL CACHE API TESTS PASSED!")
