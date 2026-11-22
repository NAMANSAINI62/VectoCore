"""Integration test: Chatbot SSE streaming with Multilingual Semantic Caching."""

import asyncio
import sys
import uuid
from pathlib import Path

# Ensure backend root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from sqlalchemy import select, delete
from app.database.session import async_session_factory
from app.models.user import User
from app.models.chat import ChatConversation, ChatMessage
from app.models.cache import CacheEntry, CacheTelemetry
from app.chatbot import graph as chatbot_graph
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda


def test_chatbot_multilingual_semantic_cache_integration(monkeypatch: pytest.MonkeyPatch):
    async def _test():
        user_id = uuid.uuid4()
        conversation_id = uuid.uuid4()
        session_factory = async_session_factory

        # 1. Create User & Conversation in real PostgreSQL DB
        async with session_factory() as session:
            user = User(
                id=user_id,
                full_name="Cache Integration User",
                email=f"cache_user_{user_id.hex[:8]}@example.com",
                password_hash="mock_hash",
            )
            session.add(user)
            await session.flush()

            conv = ChatConversation(
                id=conversation_id,
                owner_id=user_id,
                title="Test Multilingual Cache Chat",
                selected_provider="groq",
                selected_model="openai/gpt-oss-120b",
            )
            session.add(conv)
            await session.commit()

        # Mock LLM to return a predictable answer when called
        llm_called_count = 0

        def mock_llm_stream(prompt: object):
            nonlocal llm_called_count
            llm_called_count += 1
            return AIMessage(content="Python is a powerful high-level programming language.")

        monkeypatch.setattr(chatbot_graph, "validate_provider_model", lambda *_: None)
        monkeypatch.setattr(chatbot_graph, "get_chat_model", lambda *_args, **_kwargs: RunnableLambda(mock_llm_stream))

        try:
            # -----------------------------------------------------------------
            # TURN 1: Ask "What is Python?" in English -> CACHE MISS (LLM Called)
            # -----------------------------------------------------------------
            msg1_id = uuid.uuid4()
            async with session_factory() as session:
                user_msg1 = ChatMessage(
                    id=msg1_id,
                    owner_id=user_id,
                    conversation_id=conversation_id,
                    role="user",
                    content="What is Python?",
                    provider="groq",
                    model_id="openai/gpt-oss-120b",
                )
                session.add(user_msg1)
                await session.commit()

            streamed_1: list[dict] = []
            final_state_1: dict = {}
            async with session_factory() as session:
                async for mode, part in chatbot_graph.chat_graph.astream(
                    {
                        "db": session,
                        "user_id": user_id,
                        "conversation_id": conversation_id,
                        "user_message_id": msg1_id,
                        "message": "What is Python?",
                        "provider": "groq",
                        "model": "openai/gpt-oss-120b",
                    },
                    stream_mode=["custom", "values"],
                ):
                    if mode == "custom":
                        streamed_1.append(part)
                    elif mode == "values":
                        final_state_1 = part

            assert llm_called_count == 1
            assert final_state_1.get("is_cached") is False
            assert final_state_1.get("answer") == "Python is a powerful high-level programming language."

            # Verify entry stored in database
            async with session_factory() as session:
                entry = await session.scalar(
                    select(CacheEntry).where(CacheEntry.owner_id == user_id, CacheEntry.query == "What is Python?")
                )
                assert entry is not None
                assert entry.response == "Python is a powerful high-level programming language."

            # -----------------------------------------------------------------
            # TURN 2: Ask "Python क्या है?" in Hindi -> SEMANTIC CACHE HIT!
            # LLM MUST NOT BE CALLED (llm_called_count stays 1)
            # -----------------------------------------------------------------
            msg2_id = uuid.uuid4()
            async with session_factory() as session:
                user_msg2 = ChatMessage(
                    id=msg2_id,
                    owner_id=user_id,
                    conversation_id=conversation_id,
                    role="user",
                    content="Python क्या है?",
                    provider="groq",
                    model_id="openai/gpt-oss-120b",
                )
                session.add(user_msg2)
                await session.commit()

            streamed_2: list[dict] = []
            final_state_2: dict = {}
            async with session_factory() as session:
                async for mode, part in chatbot_graph.chat_graph.astream(
                    {
                        "db": session,
                        "user_id": user_id,
                        "conversation_id": conversation_id,
                        "user_message_id": msg2_id,
                        "message": "Python क्या है?",
                        "provider": "groq",
                        "model": "openai/gpt-oss-120b",
                    },
                    stream_mode=["custom", "values"],
                ):
                    if mode == "custom":
                        streamed_2.append(part)
                    elif mode == "values":
                        final_state_2 = part

            # VERIFY LLM WAS NOT CALLED!
            assert llm_called_count == 1, "LLM was called on semantic cache hit!"
            assert final_state_2.get("is_cached") is True
            assert final_state_2.get("answer") == "Python is a powerful high-level programming language."

            # Verify cache telemetry event was emitted in custom stream
            telemetry_events = [e for e in streamed_2 if e.get("event") == "cache.telemetry"]
            assert len(telemetry_events) == 1
            assert telemetry_events[0]["data"]["hit"] is True
            assert telemetry_events[0]["data"]["cache_type"] == "semantic_hit"
            assert telemetry_events[0]["data"]["similarity_score"] > 0.82

            # -----------------------------------------------------------------
            # TURN 3: Ask "What is the capital of China?" -> CRITICAL ENTITY MISS!
            # LLM MUST BE CALLED!
            # -----------------------------------------------------------------
            msg3_id = uuid.uuid4()
            async with session_factory() as session:
                user_msg3 = ChatMessage(
                    id=msg3_id,
                    owner_id=user_id,
                    conversation_id=conversation_id,
                    role="user",
                    content="What is the capital of China?",
                    provider="groq",
                    model_id="openai/gpt-oss-120b",
                )
                session.add(user_msg3)
                await session.commit()

            final_state_3: dict = {}
            async with session_factory() as session:
                async for mode, part in chatbot_graph.chat_graph.astream(
                    {
                        "db": session,
                        "user_id": user_id,
                        "conversation_id": conversation_id,
                        "user_message_id": msg3_id,
                        "message": "What is the capital of China?",
                        "provider": "groq",
                        "model": "openai/gpt-oss-120b",
                    },
                    stream_mode=["custom", "values"],
                ):
                    if mode == "values":
                        final_state_3 = part

            # LLM MUST BE CALLED!
            assert llm_called_count == 2
            assert final_state_3.get("is_cached") is False

        finally:
            # Cleanup test data
            async with session_factory() as session:
                await session.execute(delete(CacheTelemetry).where(CacheTelemetry.owner_id == user_id))
                await session.execute(delete(CacheEntry).where(CacheEntry.owner_id == user_id))
                await session.execute(delete(ChatMessage).where(ChatMessage.owner_id == user_id))
                await session.execute(delete(ChatConversation).where(ChatConversation.owner_id == user_id))
                await session.execute(delete(User).where(User.id == user_id))
                await session.commit()
            from app.database.session import engine as db_engine
            await db_engine.dispose()

    asyncio.run(_test())


if __name__ == "__main__":
    import pytest
    test_chatbot_multilingual_semantic_cache_integration(pytest.MonkeyPatch())
    print("CHATBOT MULTILINGUAL INTEGRATION TEST PASSED!")
