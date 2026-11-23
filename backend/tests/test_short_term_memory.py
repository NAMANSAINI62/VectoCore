"""Offline unit tests for short-term conversation memory (no network, SQLite + stubs)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.chatbot.graph import persist_response
from app.database.base import Base
from app.models.chat import ChatConversation, ChatMessage
from app.models.user import User
from app.services import memory_service as mem_svc


async def _make_db() -> tuple[async_sessionmaker[AsyncSession], any]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False), engine


async def _seed_user_and_conv(
    session: AsyncSession,
    *,
    email: str = "u1@example.com",
    summary: str | None = None,
) -> tuple[User, ChatConversation]:
    user = User(full_name="Test User", email=email, password_hash="hashed")
    session.add(user)
    await session.flush()
    conv = ChatConversation(
        owner_id=user.id,
        title="Memory Test",
        selected_provider="gemini",
        selected_model="gemini-3.1-flash-lite",
        summary=summary,
    )
    session.add(conv)
    await session.commit()
    return user, conv


def test_window_respects_token_budget_and_never_splits_message() -> None:
    async def _run() -> None:
        maker, engine = await _make_db()
        try:
            async with maker() as db:
                user, conv = await _seed_user_and_conv(db)
                long_a = "alpha " * 30
                long_b = "beta " * 30
                long_c = "gamma " * 30
                for idx, txt in enumerate([long_a, long_b, long_c]):
                    db.add(
                        ChatMessage(
                            owner_id=user.id,
                            conversation_id=conv.id,
                            role="user" if idx % 2 == 0 else "assistant",
                            content=txt.strip(),
                            status="completed",
                        )
                    )
                await db.commit()

                with (
                    patch.object(mem_svc, "memory_cache_get", new=AsyncMock(return_value=None)),
                    patch.object(mem_svc, "memory_cache_set", new=AsyncMock()),
                    patch.object(mem_svc, "get_model_memory_token_budget", return_value=90),
                    patch.object(mem_svc.settings, "MEMORY_ENABLED", True),
                ):
                    ctx = await mem_svc.build_context(
                        db, user.id, conv.id, "hi", "gemini-3.1-flash-lite"
                    )
                assert ctx.window_size < 3
                for msg in ctx.messages:
                    assert msg.content in (long_a.strip(), long_b.strip(), long_c.strip())
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_summary_created_after_threshold_and_is_incremental() -> None:
    async def _run() -> None:
        maker, engine = await _make_db()
        try:
            async with maker() as db:
                user, conv = await _seed_user_and_conv(db, summary="Old summary about Redis.")
                dropped = [
                    (uuid.uuid4(), "user", f"Turn {i} question")
                    for i in range(6)
                ]
                seen_old: list[str | None] = []

                async def fake_gen(old_sum: str | None, msgs: list) -> str:
                    seen_old.append(old_sum)
                    return f"{old_sum} Added {len(msgs)} turns."

                with (
                    patch.object(mem_svc.settings, "MEMORY_ENABLED", True),
                    patch.object(mem_svc.settings, "MEMORY_SUMMARY_TRIGGER_MESSAGES", 6),
                    patch.object(mem_svc.settings, "MEMORY_SUMMARY_MAX_TOKENS", 200),
                    patch.object(mem_svc, "invalidate_conversation_memory", new=AsyncMock()),
                ):
                    ok = await mem_svc.refresh_conversation_summary(
                        user.id, conv.id, dropped, db=db, summary_generator=fake_gen
                    )
                assert ok is True
                assert seen_old == ["Old summary about Redis."]
                await db.refresh(conv)
                assert conv.summary == "Old summary about Redis. Added 6 turns."
                assert conv.summary_upto_message_id == dropped[-1][0]
                assert conv.summary_updated_at is not None
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_cross_user_isolation_returns_nothing() -> None:
    async def _run() -> None:
        maker, engine = await _make_db()
        try:
            async with maker() as db:
                user1, conv1 = await _seed_user_and_conv(db, email="owner@example.com", summary="Private")
                attacker = User(full_name="Other", email="other@example.com", password_hash="hashed")
                db.add(attacker)
                await db.flush()
                db.add(
                    ChatMessage(
                        owner_id=user1.id,
                        conversation_id=conv1.id,
                        role="user",
                        content="Secret project codename Orion",
                        status="completed",
                    )
                )
                await db.commit()

                with (
                    patch.object(mem_svc, "memory_cache_get", new=AsyncMock(return_value=None)),
                    patch.object(mem_svc, "memory_cache_set", new=AsyncMock()),
                    patch.object(mem_svc.settings, "MEMORY_ENABLED", True),
                ):
                    ctx = await mem_svc.build_context(
                        db, attacker.id, conv1.id, "tell me", "gemini-3.1-flash-lite"
                    )
                assert ctx.messages == []
                assert ctx.window_size == 0
                assert ctx.summary_included is False
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_blocked_and_incomplete_messages_excluded() -> None:
    async def _run() -> None:
        maker, engine = await _make_db()
        try:
            async with maker() as db:
                user, conv = await _seed_user_and_conv(db)
                db.add_all([
                    ChatMessage(owner_id=user.id, conversation_id=conv.id, role="user", content="Safe msg", status="completed"),
                    ChatMessage(owner_id=user.id, conversation_id=conv.id, role="user", content="Blocked attack", status="blocked"),
                    ChatMessage(owner_id=user.id, conversation_id=conv.id, role="assistant", content="Partial...", status="streaming"),
                ])
                await db.commit()

                with (
                    patch.object(mem_svc, "memory_cache_get", new=AsyncMock(return_value=None)),
                    patch.object(mem_svc, "memory_cache_set", new=AsyncMock()),
                    patch.object(mem_svc.settings, "MEMORY_ENABLED", True),
                ):
                    ctx = await mem_svc.build_context(
                        db, user.id, conv.id, "next", "gemini-3.1-flash-lite"
                    )
                contents = [m.content for m in ctx.messages]
                assert contents == ["Safe msg"]
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_summary_with_secret_or_aadhaar_is_discarded() -> None:
    async def _run() -> None:
        maker, engine = await _make_db()
        try:
            async with maker() as db:
                user, conv = await _seed_user_and_conv(db, summary="Clean prior summary")
                dropped = [(uuid.uuid4(), "user", f"msg {i}") for i in range(6)]

                async def leaky_secret_gen(_old: str | None, _msgs: list) -> str:
                    return "User shared key nvapi-ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"

                async def leaky_aadhaar_gen(_old: str | None, _msgs: list) -> str:
                    return "User Aadhaar is 4921 8374 6158"

                with (
                    patch.object(mem_svc.settings, "MEMORY_ENABLED", True),
                    patch.object(mem_svc.settings, "MEMORY_SUMMARY_TRIGGER_MESSAGES", 6),
                    patch.object(mem_svc, "invalidate_conversation_memory", new=AsyncMock()),
                ):
                    ok_sec = await mem_svc.refresh_conversation_summary(
                        user.id, conv.id, dropped, db=db, summary_generator=leaky_secret_gen
                    )
                    ok_aad = await mem_svc.refresh_conversation_summary(
                        user.id, conv.id, dropped, db=db, summary_generator=leaky_aadhaar_gen
                    )
                assert ok_sec is False
                assert ok_aad is False
                await db.refresh(conv)
                assert conv.summary == "Clean prior summary"
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_redis_down_falls_back_to_postgres() -> None:
    async def _run() -> None:
        maker, engine = await _make_db()
        try:
            async with maker() as db:
                user, conv = await _seed_user_and_conv(db)
                db.add(
                    ChatMessage(
                        owner_id=user.id,
                        conversation_id=conv.id,
                        role="user",
                        content="Postgres fallback message",
                        status="completed",
                    )
                )
                await db.commit()

                with (
                    patch("app.cache.redis_client.get_redis_client", side_effect=ConnectionError("Redis down")),
                    patch.object(mem_svc.settings, "MEMORY_ENABLED", True),
                ):
                    ctx = await mem_svc.build_context(
                        db, user.id, conv.id, "hi", "gemini-3.1-flash-lite"
                    )
                assert [m.content for m in ctx.messages] == ["Postgres fallback message"]
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_memory_disabled_keeps_legacy_24_message_behavior() -> None:
    async def _run() -> None:
        maker, engine = await _make_db()
        try:
            async with maker() as db:
                user, conv = await _seed_user_and_conv(db, summary="Should not be injected")
                for i in range(30):
                    db.add(
                        ChatMessage(
                            owner_id=user.id,
                            conversation_id=conv.id,
                            role="user",
                            content=f"Legacy msg {i}",
                            status="completed",
                        )
                    )
                await db.commit()

                with patch.object(mem_svc.settings, "MEMORY_ENABLED", False):
                    ctx = await mem_svc.build_context(
                        db, user.id, conv.id, "hi", "gemini-3.1-flash-lite"
                    )
                assert ctx.summary_included is False
                assert ctx.window_size == 25  # CHAT_CONTEXT_MESSAGES + 1 legacy slice
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_memory_based_answer_not_stored_in_global_cache() -> None:
    async def _run() -> None:
        maker, engine = await _make_db()
        try:
            async with maker() as db:
                user, conv = await _seed_user_and_conv(db)
                user_msg = ChatMessage(
                    owner_id=user.id,
                    conversation_id=conv.id,
                    role="user",
                    content="Explain that in simple terms",
                    status="completed",
                )
                db.add(user_msg)
                await db.commit()

                state = {
                    "db": db,
                    "user_id": user.id,
                    "conversation_id": conv.id,
                    "user_message_id": user_msg.id,
                    "message": "Explain that in simple terms",
                    "provider": "gemini",
                    "model": "gemini-3.1-flash-lite",
                    "answer": "Here is a simpler explanation.",
                    "started_at": 0.0,
                    "usage": {"input_tokens": 10, "output_tokens": 12},
                    "is_cached": False,
                    "skip_cache": False,
                    "memory_used": True,
                    "proven_context_independent": False,
                }
                with (
                    patch("app.chatbot.graph.invalidate_conversation_memory", new=AsyncMock()),
                    patch("app.chatbot.graph.schedule_summary_refresh"),
                    patch("app.services.cache_engine.SemanticCacheEngine.store", new=AsyncMock()) as mock_store,
                    patch("app.services.cache_engine.SemanticCacheEngine.record_telemetry", new=AsyncMock()),
                ):
                    await persist_response(state)  # type: ignore[arg-type]
                    assert mock_store.await_count == 0
        finally:
            await engine.dispose()

    asyncio.run(_run())
