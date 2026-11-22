"""End-to-end tests for Multilingual Semantic Caching and Entity Isolation."""

import asyncio
import sys
from pathlib import Path

# Ensure backend root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uuid
import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config.settings import get_settings
from app.models.user import User
from app.models.cache import CacheEntry, CacheTelemetry
from app.services.cache_engine import SemanticCacheEngine


def test_multilingual_semantic_cache_lifecycle():
    print("test_multilingual_semantic_cache_lifecycle starting...", flush=True)
    async def _test():
        user_1_id = uuid.uuid4()
        user_2_id = uuid.uuid4()
        local_engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
        session_factory = async_sessionmaker(
            bind=local_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )

        try:
            # Create test users in DB to satisfy foreign key constraints
            async with session_factory() as session:
                u1 = User(id=user_1_id, full_name="Test User 1", email=f"test1_{user_1_id.hex[:8]}@example.com", password_hash="dummy")
                u2 = User(id=user_2_id, full_name="Test User 2", email=f"test2_{user_2_id.hex[:8]}@example.com", password_hash="dummy")
                session.add_all([u1, u2])
                await session.commit()

            # =========================================================================
            # SCENARIO 1: CROSS-LANGUAGE SEMANTIC CACHE HIT (English -> Hindi -> Hinglish)
            # =========================================================================
            print("--> Starting Scenario 1: Cross-language hit...", flush=True)
            async with session_factory() as session:
                engine_u1 = SemanticCacheEngine(session, user_1_id)

                # 1. User 1 asks "What is Python?" -> MISS
                lookup_1 = await engine_u1.lookup("What is Python?", "groq", "openai/gpt-oss-120b")
                assert lookup_1.hit is False
                assert lookup_1.cache_type == "miss"

                # Store LLM answer
                python_response = "Python is a high-level programming language known for readable syntax."
                await engine_u1.store(
                    query="What is Python?",
                    response=python_response,
                    provider="groq",
                    model="openai/gpt-oss-120b",
                    input_tokens=15,
                    output_tokens=350,
                )

                # 2. Hindi Query: "Python क्या है?" -> SEMANTIC HIT!
                lookup_hindi = await engine_u1.lookup("Python क्या है?", "groq", "openai/gpt-oss-120b")
                assert lookup_hindi.hit is True
                assert lookup_hindi.cache_type == "semantic_hit"
                assert lookup_hindi.response == python_response
                assert lookup_hindi.similarity_score > 0.82

                # 3. Hinglish Query: "Python ka meaning kya hai?" -> SEMANTIC HIT!
                lookup_hinglish = await engine_u1.lookup("Python ka meaning kya hai?", "groq", "openai/gpt-oss-120b")
                assert lookup_hinglish.hit is True
                assert lookup_hinglish.cache_type == "semantic_hit"
                assert lookup_hinglish.response == python_response
                assert lookup_hinglish.similarity_score > 0.82

                # 4. Paraphrase English Query: "Explain Python programming language." -> SEMANTIC HIT!
                lookup_para = await engine_u1.lookup("Explain Python programming language.", "groq", "openai/gpt-oss-120b")
                assert lookup_para.hit is True
                assert lookup_para.response == python_response
            print("--> Scenario 1 PASSED!", flush=True)

            # =========================================================================
            # SCENARIO 2: CRITICAL ENTITY ISOLATION (India vs China vs Delhi)
            # =========================================================================
            async with session_factory() as session:
                engine_u1 = SemanticCacheEngine(session, user_1_id)

                # Store India Capital
                await engine_u1.store(
                    query="What is the capital of India?",
                    response="The capital of India is New Delhi.",
                    provider="groq",
                    model="openai/gpt-oss-120b",
                    input_tokens=10,
                    output_tokens=20,
                )

                # Query China -> MUST BE MISS (Entity China != India)
                lookup_china = await engine_u1.lookup("What is the capital of China?", "groq", "openai/gpt-oss-120b")
                assert lookup_china.hit is False
                assert lookup_china.cache_type == "miss"

                # Query Delhi -> MUST BE MISS (Entity Delhi != India)
                lookup_delhi = await engine_u1.lookup("What is the capital of Delhi?", "groq", "openai/gpt-oss-120b")
                assert lookup_delhi.hit is False
                assert lookup_delhi.cache_type == "miss"

            # =========================================================================
            # SCENARIO 3: INTENT ISOLATION (Definition vs Advantages vs Installation)
            # =========================================================================
            async with session_factory() as session:
                engine_u1 = SemanticCacheEngine(session, user_1_id)

                # "What are the advantages of Python?" -> MUST BE MISS (Intent advantages != definition)
                lookup_adv = await engine_u1.lookup("What are the advantages of Python?", "groq", "openai/gpt-oss-120b")
                assert lookup_adv.hit is False
                assert lookup_adv.cache_type == "miss"

                # "How do I install Python?" -> MUST BE MISS (Intent installation != definition)
                lookup_inst = await engine_u1.lookup("How do I install Python?", "groq", "openai/gpt-oss-120b")
                assert lookup_inst.hit is False
                assert lookup_inst.cache_type == "miss"

            # =========================================================================
            # SCENARIO 4: BRIEF VS DETAILED SCOPE ISOLATION
            # =========================================================================
            async with session_factory() as session:
                engine_u1 = SemanticCacheEngine(session, user_1_id)

                # "What is Python in detail?" -> MUST BE MISS (depth_scope detailed != standard)
                lookup_det = await engine_u1.lookup("Explain Python in detail with complete code", "groq", "openai/gpt-oss-120b")
                assert lookup_det.hit is False
                assert lookup_det.cache_type == "miss"

            # =========================================================================
            # SCENARIO 5: USER TENANT ISOLATION (User 2 cannot access User 1's cache)
            # =========================================================================
            async with session_factory() as session:
                engine_u2 = SemanticCacheEngine(session, user_2_id)

                # User 2 asks same question -> MUST BE MISS (Private isolation)
                lookup_u2 = await engine_u2.lookup("What is Python?", "groq", "openai/gpt-oss-120b")
                assert lookup_u2.hit is False
                assert lookup_u2.cache_type == "miss"

        finally:
            try:
                async with session_factory() as session:
                    await session.execute(delete(CacheTelemetry).where(CacheTelemetry.owner_id.in_([user_1_id, user_2_id])))
                    await session.execute(delete(CacheEntry).where(CacheEntry.owner_id.in_([user_1_id, user_2_id])))
                    await session.execute(delete(User).where(User.id.in_([user_1_id, user_2_id])))
                    await session.commit()
            finally:
                await local_engine.dispose()
                await asyncio.sleep(0)

    asyncio.run(_test())


if __name__ == "__main__":
    test_multilingual_semantic_cache_lifecycle()
    print("ALL SCENARIOS PASSED SUCCESSFULLY!")

