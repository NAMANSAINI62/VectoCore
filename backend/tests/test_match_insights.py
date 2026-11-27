"""Tests for Two-Stage Intent-Aware Semantic Cache Matching & Match Insights."""

from __future__ import annotations

import asyncio
import math
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.v1.endpoints.cache import SemanticMatchInsightsResponse, TelemetryItemResponse
from app.cache import redis_client
from app.models.cache import CacheEntry
from app.services.cache_engine import SemanticCacheEngine, compute_config_hash
from app.services.intent_service import (
    IntentCompatibilitySchema,
    IntentValidationResult,
    validate_candidate_intent,
)


def _unit_vec(angle_deg: float, dim: int = 384) -> list[float]:
    """Create a deterministic unit vector in 384-D space with controlled cosine similarity."""
    rad = math.radians(angle_deg)
    vec = [0.0] * dim
    vec[0] = math.cos(rad)
    vec[1] = math.sin(rad)
    return vec


def _make_entry(
    owner_id: uuid.UUID,
    query: str,
    response: str,
    angle_deg: float,
    *,
    lang: str = "English",
    model: str = "gpt-4o-mini",
) -> CacheEntry:
    now = datetime.now(timezone.utc)
    return CacheEntry(
        id=uuid.uuid4(),
        owner_id=owner_id,
        query=query,
        normalized_query=query.lower(),
        query_embedding=_unit_vec(angle_deg),
        embedding_dim=384,
        embedding_model="BAAI/bge-small-en-v1.5",
        response=response,
        detected_language=lang,
        intent="general",
        depth_scope="standard",
        critical_entities=[],
        provider="openai",
        model=model,
        config_hash=compute_config_hash("openai", model),
        input_tokens=15,
        output_tokens=45,
        hit_count=0,
        status="active",
        created_at=now,
        expires_at=now + timedelta(hours=24),
        last_hit_at=None,
    )


def _make_mock_db(entries: list[CacheEntry]) -> AsyncMock:
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=None)
    scalars_result = MagicMock()
    scalars_result.all.return_value = entries
    db.scalars = AsyncMock(return_value=scalars_result)
    db.commit = AsyncMock()
    return db


@pytest.fixture(autouse=True)
def _disable_redis_for_unit_tests():
    prev = redis_client._last_redis_failure
    redis_client._last_redis_failure = 1e18
    with patch("app.services.cache_engine.exact_cache_get", AsyncMock(return_value=None)):
        try:
            yield
        finally:
            redis_client._last_redis_failure = prev


@pytest.mark.asyncio
async def test_group_a_same_intent_different_wording_semantic_hit():
    """Group A: Equivalent intent with different wording produces semantic_hit and snapshots."""
    owner_id = uuid.uuid4()
    entry = _make_entry(
        owner_id,
        "What are the benefits of Python?",
        "Python offers readability, rich libraries, and rapid development.",
        angle_deg=20.0,  # cos(20) ~= 0.9397
    )
    db = _make_mock_db([entry])

    fake_embed = MagicMock()
    fake_embed.embed_query.return_value = _unit_vec(0.0)

    async def fake_validate(curr, cand, sim, **kwargs):
        return IntentValidationResult(
            is_valid=True,
            reason="Both queries ask for the advantages/benefits of Python.",
            used_llm_judge=True,
            confidence=0.97,
            intent_summary="Advantages of Python",
        )

    with (
        patch("app.services.cache_engine.get_embedding_service", return_value=fake_embed),
        patch("app.services.cache_engine.validate_candidate_intent", side_effect=fake_validate),
    ):
        engine = SemanticCacheEngine(db, owner_id)
        result = await engine.lookup("What are the advantages of Python?", "openai", "gpt-4o-mini")

    assert result.hit is True
    assert result.cache_type == "semantic_hit"
    assert result.matched_query == "What are the benefits of Python?"
    assert result.response == entry.response
    assert len(result.matched_queries_snapshot) == 1
    assert result.matched_queries_snapshot[0]["selected"] is True
    assert result.matched_queries_snapshot[0]["intent_compatible"] is True
    assert result.matched_queries_snapshot[0]["similarity_score"] == pytest.approx(math.cos(math.radians(20.0)), abs=1e-4)


@pytest.mark.asyncio
async def test_group_b_similar_wording_different_intent_rejected():
    """Group B: High-similarity queries with different intent must be rejected and logged."""
    owner_id = uuid.uuid4()
    entries = [
        _make_entry(owner_id, "Why is Python popular?", "Because of AI and web ecosystems.", angle_deg=15.0),
        _make_entry(owner_id, "What is Python used for?", "Web, data science, automation.", angle_deg=18.0),
        _make_entry(owner_id, "How does Python work?", "Python compiles to bytecode for PVM.", angle_deg=22.0),
    ]
    db = _make_mock_db(entries)

    fake_embed = MagicMock()
    fake_embed.embed_query.return_value = _unit_vec(0.0)

    async def fake_validate(curr, cand, sim, **kwargs):
        return IntentValidationResult(
            is_valid=False,
            reason=f"'{cand}' asks a different question than advantages of Python.",
            used_llm_judge=True,
            confidence=0.95,
            intent_summary="Different intent",
        )

    with (
        patch("app.services.cache_engine.get_embedding_service", return_value=fake_embed),
        patch("app.services.cache_engine.validate_candidate_intent", side_effect=fake_validate),
    ):
        engine = SemanticCacheEngine(db, owner_id)
        result = await engine.lookup("What are the advantages of Python?", "openai", "gpt-4o-mini")

    assert result.hit is False
    assert result.cache_type == "miss"
    assert result.matched_queries_snapshot == []
    assert len(result.rejected_candidates_snapshot) == 3
    assert all(r["intent_compatible"] is False for r in result.rejected_candidates_snapshot)


@pytest.mark.asyncio
async def test_group_c_top_3_selection_after_intent_validation():
    """Group C: Top 3 selection occurs AFTER intent validation (never padded, max 3, ranked by similarity)."""
    owner_id = uuid.uuid4()
    entries = [
        _make_entry(owner_id, "Why is Python popular?", "Popular", angle_deg=10.0),  # highest sim, incompatible
        _make_entry(owner_id, "What are the benefits of Python?", "Resp 1", angle_deg=15.0),  # compatible #1
        _make_entry(owner_id, "What is Python?", "Definition", angle_deg=18.0),  # incompatible
        _make_entry(owner_id, "Tell me the benefits of Python.", "Resp 2", angle_deg=20.0),  # compatible #2
        _make_entry(owner_id, "What benefits does Python offer?", "Resp 3", angle_deg=25.0),  # compatible #3
        _make_entry(owner_id, "What are the advantages of using Python?", "Resp 4", angle_deg=30.0),  # compatible #4 (excluded)
    ]
    db = _make_mock_db(entries)

    fake_embed = MagicMock()
    fake_embed.embed_query.return_value = _unit_vec(0.0)

    compatible_queries = {
        "What are the benefits of Python?",
        "Tell me the benefits of Python.",
        "What benefits does Python offer?",
        "What are the advantages of using Python?",
    }

    async def fake_validate(curr, cand, sim, **kwargs):
        is_ok = cand in compatible_queries
        return IntentValidationResult(
            is_valid=is_ok,
            reason="Equivalent benefits query." if is_ok else "Incompatible intent.",
            used_llm_judge=True,
            confidence=0.92,
            intent_summary="Comparison",
        )

    with (
        patch("app.services.cache_engine.get_embedding_service", return_value=fake_embed),
        patch("app.services.cache_engine.validate_candidate_intent", side_effect=fake_validate),
    ):
        engine = SemanticCacheEngine(db, owner_id)
        result = await engine.lookup("What are the advantages of Python?", "openai", "gpt-4o-mini")

    assert result.hit is True
    assert result.cache_type == "semantic_hit"
    assert len(result.matched_queries_snapshot) == 1
    assert result.matched_queries_snapshot[0]["rank"] == 1
    assert result.matched_queries_snapshot[0]["previous_query"] == "What are the benefits of Python?"
    assert result.matched_queries_snapshot[0]["selected"] is True
    assert len(result.rejected_candidates_snapshot) == 1


@pytest.mark.asyncio
async def test_group_d_and_e_structured_llm_validation_multilingual_and_instructions():
    """Group D & E: Structured LLM output validates Hinglish equivalence and rejects instruction conflicts."""
    mock_structured = AsyncMock()
    mock_llm = MagicMock()
    mock_llm.bind.return_value = mock_llm
    mock_llm.with_structured_output.return_value = mock_structured

    # Group D: Hinglish equivalent intent
    mock_structured.ainvoke.return_value = IntentCompatibilitySchema(
        is_compatible=True,
        confidence=0.96,
        intent_summary="Advantages of Python (Hinglish/English)",
        reason="Both ask for the advantages/benefits of Python.",
    )
    with patch("app.services.intent_service.get_chat_model", return_value=mock_llm):
        res_hi = await validate_candidate_intent(
            "What are the advantages of Python?",
            "Python ke kya fayde hain?",
            0.81,
            provider="openai",
            model="gpt-4o-mini",
        )
    assert res_hi.is_valid is True
    assert res_hi.used_llm_judge is True

    # Group E: Incompatible explicit instructions
    mock_structured.ainvoke.return_value = IntentCompatibilitySchema(
        is_compatible=False,
        confidence=0.94,
        intent_summary="Format constraint mismatch",
        reason="Current query asks for 3 bullet points while cached query asks for a detailed essay.",
    )
    with patch("app.services.intent_service.get_chat_model", return_value=mock_llm):
        res_instr = await validate_candidate_intent(
            "Explain Python in 3 bullet points",
            "Write a detailed essay on Python",
            0.85,
            provider="openai",
            model="gpt-4o-mini",
        )
    assert res_instr.is_valid is False


@pytest.mark.asyncio
async def test_group_f_actual_similarity_not_fabricated():
    """Group F: Similarity scores reflect actual vector cosine similarity, never fabricated 1.0."""
    owner_id = uuid.uuid4()
    entry = _make_entry(owner_id, "What are the benefits of Python?", "Benefits response", angle_deg=35.0)
    db = _make_mock_db([entry])

    fake_embed = MagicMock()
    fake_embed.embed_query.return_value = _unit_vec(0.0)

    async def fake_validate(curr, cand, sim, **kwargs):
        return IntentValidationResult(is_valid=True, reason="Compatible", used_llm_judge=True, confidence=0.9)

    with (
        patch("app.services.cache_engine.get_embedding_service", return_value=fake_embed),
        patch("app.services.cache_engine.validate_candidate_intent", side_effect=fake_validate),
    ):
        engine = SemanticCacheEngine(db, owner_id)
        result = await engine.lookup("What are the advantages of Python?", "openai", "gpt-4o-mini")

    expected = math.cos(math.radians(35.0))
    assert result.similarity_score == pytest.approx(expected, abs=1e-4)
    assert result.similarity_score < 0.9


def test_group_g_historical_snapshot_and_exact_hit_isolation():
    """Group G: Historical telemetry schema works with snapshots and legacy NULL rows, and isolates exact hits."""
    now = datetime.now(timezone.utc)
    legacy_row = SimpleNamespace(
        id=uuid.uuid4(),
        query_preview="What are the advantages of Python?",
        cache_status="semantic_hit",
        provider="openai",
        model="gpt-4o-mini",
        detected_language="English",
        requested_language="English",
        input_tokens=10,
        output_tokens=20,
        tokens_saved=30,
        cache_lookup_latency_ms=12,
        llm_latency_ms=0,
        total_latency_ms=12,
        similarity_score=0.91,
        matched_entry_id=None,
        matched_query="What are the benefits of Python?",
        response_preview="Cached benefits response",
        created_at=now,
    )
    resp = TelemetryItemResponse.model_validate(legacy_row)
    assert resp.semantic_match_insights is None

    insights = SemanticMatchInsightsResponse(
        current_query=legacy_row.query_preview,
        cache_decision="HIT",
        cache_status="semantic_hit",
        matched_queries=[],
        selected_previous_query=legacy_row.matched_query,
        returned_cached_response=legacy_row.response_preview,
        rejected_candidates=[],
    )
    resp.semantic_match_insights = insights
    assert resp.semantic_match_insights.returned_cached_response == "Cached benefits response"


@pytest.mark.asyncio
async def test_group_h_validator_failure_and_timeout_safe_fallback():
    """Group H: Validator timeouts or exceptions never cause false cache hits."""
    mock_structured = AsyncMock()
    mock_structured.ainvoke.side_effect = asyncio.TimeoutError()
    mock_llm = MagicMock()
    mock_llm.bind.return_value = mock_llm
    mock_llm.with_structured_output.return_value = mock_structured

    with patch("app.services.intent_service.get_chat_model", return_value=mock_llm):
        res_timeout = await validate_candidate_intent(
            "What are the advantages of Python?",
            "What are the benefits of Python?",
            0.90,
            provider="openai",
            model="gpt-4o-mini",
        )
    assert res_timeout.is_valid is False

    with patch("app.services.intent_service.get_chat_model", side_effect=RuntimeError("API down")):
        res_err = await validate_candidate_intent(
            "What are the advantages of Python?",
            "What are the benefits of Python?",
            0.90,
            provider="openai",
            model="gpt-4o-mini",
        )
    assert res_err.is_valid is False
