"""FastAPI endpoints for cache entries, request telemetry, and analytics."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db_session
from app.dependencies.auth import get_current_user
from app.models.cache import CacheEntry, CacheSettings, CacheTelemetry
from app.models.chat import ChatMessage
from app.models.user import User
from app.services.cache_engine import (
    DEFAULT_BORDERLINE_RECALL_FLOOR,
    DEFAULT_CACHE_TTL_HOURS,
    DEFAULT_SIMILARITY_THRESHOLD,
    cosine_similarity,
    query_similar_cache_entries,
)
from app.services.embedding_service import DEFAULT_EMBEDDING_DIM, DEFAULT_MODEL_NAME, EmbeddingService
router = APIRouter(prefix="/cache", tags=["Semantic Cache"])


# -----------------------------------------------------------------------------
# Pydantic Schemas
# -----------------------------------------------------------------------------

class CacheEntryResponse(BaseModel):
    id: uuid.UUID
    query: str
    normalized_query: str
    response: str
    detected_language: str
    intent: str
    depth_scope: str
    critical_entities: list[str]
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    hit_count: int
    status: str
    created_at: datetime
    expires_at: datetime
    last_hit_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class CacheEntriesPaginatedResponse(BaseModel):
    items: list[CacheEntryResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class RelatedCacheMatchItem(BaseModel):
    entry_id: str
    query: str
    similarity_score: float
    detected_language: str = "English"
    model: str = ""
    hit_count: int = 0


class SemanticMatchCandidateItem(BaseModel):
    rank: Optional[int] = None
    cache_entry_id: Optional[str] = None
    previous_query: str
    similarity_score: float
    intent_compatible: bool
    intent_status: str
    confidence: float = 0.0
    intent_summary: str = ""
    reason: str = ""
    detected_language: str = "English"
    model: str = ""
    selected: bool = False


class SemanticMatchInsightsResponse(BaseModel):
    current_query: str
    cache_decision: str
    cache_status: str
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD
    stage2_recall_floor: float = DEFAULT_BORDERLINE_RECALL_FLOOR
    matched_queries: list[SemanticMatchCandidateItem] = []
    selected_cache_entry_id: Optional[str] = None
    selected_previous_query: Optional[str] = None
    returned_cached_response: Optional[str] = None
    validation_explanation: Optional[str] = None
    rejected_candidates: list[SemanticMatchCandidateItem] = []


class TelemetryItemResponse(BaseModel):
    id: uuid.UUID
    request_id: str = ""
    query_preview: str
    cache_status: str
    provider: str
    model: str
    detected_language: str
    requested_language: str = "en"
    input_tokens: int
    output_tokens: int
    tokens_saved: int
    cache_lookup_latency_ms: int
    llm_latency_ms: int = 0
    total_latency_ms: int
    similarity_score: Optional[float] = None
    matched_entry_id: Optional[uuid.UUID] = None
    matched_query: Optional[str] = None
    response_preview: Optional[str] = None
    related_candidates: Optional[list[RelatedCacheMatchItem]] = None
    variant_reused: bool = False
    translation_performed: bool = False
    translation_failed: bool = False
    translation_latency_ms: int = 0
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    memory_context_tokens: int = 0
    memory_summary_included: bool = False
    memory_window_size: int = 0
    semantic_match_insights: Optional[SemanticMatchInsightsResponse] = None
    created_at: datetime
    model_config = {"from_attributes": True}


class DailyTrendPoint(BaseModel):
    date: str
    hits: int
    misses: int
    exact_hits: int = 0
    semantic_hits: int = 0
    requests: int
    hit_rate_pct: float = 0.0
    tokens_saved: int
    input_tokens_saved: int = 0
    output_tokens_saved: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    avg_latency_ms: float


class LatencyBucketStat(BaseModel):
    bucket: str
    exact_hits: int = 0
    semantic_hits: int = 0
    misses: int = 0
    count: int = 0


class ModelUsageStat(BaseModel):
    provider: str
    model: str
    requests: int
    hits: int
    misses: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    tokens_saved: int
    avg_latency_ms: float


class EmbeddingModelInfo(BaseModel):
    name: str
    dimensions: int
    status: str = "active"


class CacheStatsResponse(BaseModel):
    total_requests: int
    cache_hits: int
    cache_misses: int
    hit_rate_pct: float
    exact_hits: int
    semantic_hits: int
    exact_hit_rate_pct: float = 0.0
    semantic_hit_rate_pct: float = 0.0
    llm_calls_avoided: int = 0
    variant_reused_count: int = 0
    translation_operations: int = 0
    translation_failures: int = 0
    avg_translation_latency_ms: float = 0.0
    answer_llm_calls: int = 0
    translation_llm_calls: int = 0
    real_tokens_saved: int
    input_tokens_saved: int = 0
    output_tokens_saved: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    avg_hit_latency_ms: float
    avg_exact_hit_latency_ms: float = 0.0
    avg_semantic_hit_latency_ms: float = 0.0
    avg_miss_latency_ms: float
    avg_overall_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    p50_hit_latency_ms: float = 0.0
    p95_hit_latency_ms: float = 0.0
    p99_hit_latency_ms: float = 0.0
    p50_miss_latency_ms: float = 0.0
    p95_miss_latency_ms: float = 0.0
    p99_miss_latency_ms: float = 0.0
    total_entries_count: int
    recent_activity: list[TelemetryItemResponse]
    daily_trends: list[DailyTrendPoint] = []
    model_usage: list[ModelUsageStat] = []
    latency_buckets: list[LatencyBucketStat] = []
    embedding_model_info: Optional[EmbeddingModelInfo] = None


class CacheSettingsPayload(BaseModel):
    similarity_threshold: float = Field(ge=0.50, le=0.99, default=DEFAULT_SIMILARITY_THRESHOLD)
    default_ttl_hours: int = Field(ge=1, le=720, default=DEFAULT_CACHE_TTL_HOURS)


class CacheSettingsResponse(BaseModel):
    similarity_threshold: float
    default_ttl_hours: int


def _compute_percentiles(values: list[int | float]) -> tuple[float, float, float]:
    """Compute P50, P95, and P99 latency percentiles using NumPy."""
    if not values:
        return (0.0, 0.0, 0.0)
    arr = np.asarray(values, dtype=float)
    p50, p95, p99 = np.percentile(arr, [50, 95, 99])
    return (round(float(p50), 1), round(float(p95), 1), round(float(p99), 1))


def _build_telemetry_item(t: CacheTelemetry) -> tuple[TelemetryItemResponse, bool]:
    is_hit = t.cache_status in ("exact_hit", "semantic_hit")
    llm_ms = int(
        getattr(t, "llm_latency_ms", 0)
        or (0 if is_hit else max(0, (t.total_latency_ms or 0) - (t.cache_lookup_latency_ms or 0)))
    )
    item_resp = TelemetryItemResponse.model_validate(t)
    item_resp.request_id = f"req-{str(t.id)[:8]}"
    item_resp.llm_latency_ms = llm_ms
    if item_resp.response_preview and (
        "missinggreenlet" in item_resp.response_preview.lower()
        or "greenlet_spawn" in item_resp.response_preview.lower()
    ):
        item_resp.response_preview = (
            "We're sorry — this request encountered a temporary processing issue. Please try again."
        )
    return item_resp, is_hit


def _build_semantic_match_insights(
    t: CacheTelemetry,
    item_resp: TelemetryItemResponse,
    *,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> Optional[SemanticMatchInsightsResponse]:
    """Build SemanticMatchInsightsResponse from persisted snapshots with legacy fallback."""
    if t.cache_status not in ("semantic_hit", "miss"):
        return None

    matched_entry_id = item_resp.matched_entry_id or t.matched_entry_id
    matched_query = item_resp.matched_query or t.matched_query
    response_preview = item_resp.response_preview or t.response_preview

    raw_matched = getattr(t, "matched_queries_snapshot", None) or []
    if not raw_matched and t.cache_status == "semantic_hit" and matched_query:
        raw_matched = [
            {
                "rank": 1,
                "cache_entry_id": str(matched_entry_id) if matched_entry_id else None,
                "previous_query": matched_query,
                "similarity_score": round(float(t.similarity_score or 0.0), 4),
                "intent_compatible": True,
                "intent_status": "Compatible",
                "confidence": 1.0,
                "intent_summary": "Historical semantic cache hit",
                "reason": getattr(t, "validation_explanation", None) or "Matched cached query.",
                "detected_language": t.detected_language,
                "model": t.model,
                "selected": True,
            }
        ]

    raw_rejected = getattr(t, "rejected_candidates_snapshot", None) or []
    return SemanticMatchInsightsResponse(
        current_query=getattr(t, "current_query", None) or t.query_preview,
        cache_decision="HIT" if t.cache_status == "semantic_hit" else "MISS",
        cache_status=t.cache_status,
        similarity_threshold=round(float(similarity_threshold), 4),
        stage2_recall_floor=round(float(min(similarity_threshold, DEFAULT_BORDERLINE_RECALL_FLOOR)), 4),
        matched_queries=[
            SemanticMatchCandidateItem.model_validate(m) for m in raw_matched[:1]
        ],
        selected_cache_entry_id=(
            str(matched_entry_id)
            if (t.cache_status == "semantic_hit" and matched_entry_id)
            else None
        ),
        selected_previous_query=matched_query if t.cache_status == "semantic_hit" else None,
        returned_cached_response=(
            (getattr(t, "returned_response_snapshot", None) or response_preview)
            if t.cache_status == "semantic_hit"
            else None
        ),
        validation_explanation=getattr(t, "validation_explanation", None),
        rejected_candidates=[
            SemanticMatchCandidateItem.model_validate(r) for r in raw_rejected
        ],
    )


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------

@router.get("/entries", response_model=CacheEntriesPaginatedResponse)
async def list_cache_entries(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    language: Optional[str] = Query(None),
    intent: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> CacheEntriesPaginatedResponse:
    """List semantic cache entries with search and filters."""
    now = datetime.now(timezone.utc)
    query = select(CacheEntry).where(
        CacheEntry.owner_id == user.id,
        CacheEntry.status == "active",
        CacheEntry.expires_at > now,
    )

    if search:
        search_filter = f"%{search.strip().lower()}%"
        query = query.where(CacheEntry.normalized_query.ilike(search_filter) | CacheEntry.response.ilike(search_filter))
    if language:
        lang_val = language.strip().lower()
        lang_aliases = {
            "en": ["en", "english"],
            "english": ["en", "english"],
            "hi": ["hi", "hindi"],
            "hindi": ["hi", "hindi"],
            "hinglish": ["hinglish"],
            "es": ["es", "spanish"],
            "spanish": ["es", "spanish"],
            "fr": ["fr", "french"],
            "french": ["fr", "french"],
        }.get(lang_val, [lang_val])
        query = query.where(func.lower(CacheEntry.detected_language).in_(lang_aliases))
    if intent:
        query = query.where(CacheEntry.intent == intent.strip().lower())

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.scalar(count_query)) or 0

    items_query = query.order_by(CacheEntry.last_hit_at.desc().nullslast(), CacheEntry.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.scalars(items_query)
    entries = list(result.all())

    if entries:
        hit_telemetry_rows = list(
            (
                await db.scalars(
                    select(CacheTelemetry).where(
                        CacheTelemetry.owner_id == user.id,
                        CacheTelemetry.cache_status.in_(["exact_hit", "semantic_hit"]),
                    )
                )
            ).all()
        )
        dirty = False
        for e in entries:
            e_query_lower = (e.query or "").strip().lower()
            matched_hits = 0
            for t in hit_telemetry_rows:
                if t.matched_entry_id == e.id:
                    matched_hits += 1
                elif t.matched_entry_id is None:
                    t_q = (t.matched_query or t.query_preview or "").strip().lower()
                    if t_q and (t_q == e_query_lower or e_query_lower.startswith(t_q[:80])):
                        matched_hits += 1
            if matched_hits > int(e.hit_count or 0):
                e.hit_count = matched_hits
                dirty = True
        if dirty:
            await db.commit()

    total_pages = max(1, (total + page_size - 1) // page_size)

    return CacheEntriesPaginatedResponse(
        items=[CacheEntryResponse.model_validate(e) for e in entries],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.delete("/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cache_entry(
    entry_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    """Invalidate or delete a single cache entry."""
    entry = await db.scalar(
        select(CacheEntry).where(CacheEntry.id == entry_id, CacheEntry.owner_id == user.id)
    )
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cache entry not found")

    await db.delete(entry)
    await db.commit()


@router.get("/stats", response_model=CacheStatsResponse)
async def get_cache_stats(
    days: Optional[int] = Query(default=None, ge=1, le=365),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    activity_limit: int = Query(default=10, ge=1, le=1000),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> CacheStatsResponse:
    """Get live cache telemetry, latency percentiles, and input/output token usage."""
    now = datetime.now(timezone.utc)
    total_entries = (await db.scalar(
        select(func.count()).select_from(CacheEntry).where(
            CacheEntry.owner_id == user.id,
            CacheEntry.status == "active",
            CacheEntry.expires_at > now,
        )
    )) or 0

    telemetry_where: list[Any] = [CacheTelemetry.owner_id == user.id]
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
            telemetry_where.append(CacheTelemetry.created_at >= start_dt)
        except ValueError:
            pass
    elif days is not None:
        telemetry_where.append(CacheTelemetry.created_at >= now - timedelta(days=days))

    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date).replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
            telemetry_where.append(CacheTelemetry.created_at <= end_dt)
        except ValueError:
            pass

    recent_activity_rows = list((await db.scalars(
        select(CacheTelemetry)
        .where(*telemetry_where)
        .order_by(CacheTelemetry.created_at.desc())
        .limit(activity_limit)
    )).all())

    user_settings = await db.scalar(
        select(CacheSettings).where(CacheSettings.owner_id == user.id)
    )
    eff_threshold = (
        float(user_settings.similarity_threshold)
        if user_settings is not None
        else DEFAULT_SIMILARITY_THRESHOLD
    )

    is_hit_cond = CacheTelemetry.cache_status.in_(("exact_hit", "semantic_hit"))
    is_miss_cond = CacheTelemetry.cache_status == "miss"
    tz_offset = datetime.now().astimezone().utcoffset() or timedelta(0)
    local_ts = CacheTelemetry.created_at.op("AT TIME ZONE")("UTC") + tz_offset

    hit_lat_expr = case((is_hit_cond, CacheTelemetry.cache_lookup_latency_ms), else_=None)
    miss_lat_expr = case((is_miss_cond, CacheTelemetry.total_latency_ms), else_=None)
    trans_lat_expr = case(
        (CacheTelemetry.translation_performed.is_(True) & (CacheTelemetry.translation_latency_ms > 0), CacheTelemetry.translation_latency_ms),
        else_=None,
    )

    summary_row = (
        await db.execute(
            select(
                func.count().label("total_requests"),
                func.count().filter(CacheTelemetry.cache_status == "exact_hit").label("exact_hits"),
                func.count().filter(CacheTelemetry.cache_status == "semantic_hit").label("semantic_hits"),
                func.count().filter(is_miss_cond).label("miss_count"),
                func.count().filter(CacheTelemetry.variant_reused.is_(True)).label("variant_reused_count"),
                func.count().filter(CacheTelemetry.translation_performed.is_(True)).label("translation_operations"),
                func.count().filter(CacheTelemetry.translation_failed.is_(True)).label("translation_failures"),
                func.avg(trans_lat_expr).label("avg_translation_latency_ms"),
                func.count().filter(is_miss_cond).label("answer_llm_calls"),
                func.coalesce(func.sum(func.coalesce(CacheTelemetry.tokens_saved, 0)), 0).label("real_tokens_saved"),
                func.coalesce(func.sum(func.coalesce(CacheTelemetry.input_tokens, 0)).filter(is_hit_cond), 0).label("input_tokens_saved"),
                func.coalesce(func.sum(func.coalesce(CacheTelemetry.output_tokens, 0)).filter(is_hit_cond), 0).label("output_tokens_saved"),
                func.coalesce(func.sum(func.coalesce(CacheTelemetry.input_tokens, 0)), 0).label("total_input_tokens"),
                func.coalesce(func.sum(func.coalesce(CacheTelemetry.output_tokens, 0)), 0).label("total_output_tokens"),
                func.avg(hit_lat_expr).label("avg_hit_latency"),
                func.avg(case((CacheTelemetry.cache_status == "exact_hit", CacheTelemetry.cache_lookup_latency_ms), else_=None)).label("avg_exact_hit_latency"),
                func.avg(case((CacheTelemetry.cache_status == "semantic_hit", CacheTelemetry.cache_lookup_latency_ms), else_=None)).label("avg_semantic_hit_latency"),
                func.avg(miss_lat_expr).label("avg_miss_latency"),
                func.avg(CacheTelemetry.total_latency_ms).label("avg_overall_latency"),
                func.percentile_cont(0.5).within_group(CacheTelemetry.total_latency_ms).label("p50_all"),
                func.percentile_cont(0.95).within_group(CacheTelemetry.total_latency_ms).label("p95_all"),
                func.percentile_cont(0.99).within_group(CacheTelemetry.total_latency_ms).label("p99_all"),
                func.percentile_cont(0.5).within_group(hit_lat_expr).label("p50_hit"),
                func.percentile_cont(0.95).within_group(hit_lat_expr).label("p95_hit"),
                func.percentile_cont(0.99).within_group(hit_lat_expr).label("p99_hit"),
                func.percentile_cont(0.5).within_group(miss_lat_expr).label("p50_miss"),
                func.percentile_cont(0.95).within_group(miss_lat_expr).label("p95_miss"),
                func.percentile_cont(0.99).within_group(miss_lat_expr).label("p99_miss"),
                func.count(func.distinct(func.date_trunc("day", local_ts))).label("distinct_days_count"),
            ).where(*telemetry_where)
        )
    ).one()

    total_requests = int(summary_row.total_requests or 0)
    exact_hits = int(summary_row.exact_hits or 0)
    semantic_hits = int(summary_row.semantic_hits or 0)
    cache_hits = exact_hits + semantic_hits
    cache_misses = int(summary_row.miss_count or 0)

    hit_rate_pct = round((cache_hits / total_requests * 100.0), 1) if total_requests > 0 else 0.0
    exact_hit_rate_pct = round((exact_hits / total_requests * 100.0), 1) if total_requests > 0 else 0.0
    semantic_hit_rate_pct = round((semantic_hits / total_requests * 100.0), 1) if total_requests > 0 else 0.0
    variant_reused_count = int(summary_row.variant_reused_count or 0)
    translation_operations = int(summary_row.translation_operations or 0)
    translation_failures = int(summary_row.translation_failures or 0)
    avg_translation_latency_ms = round(float(summary_row.avg_translation_latency_ms), 1) if summary_row.avg_translation_latency_ms is not None else 0.0
    answer_llm_calls = int(summary_row.answer_llm_calls or 0)
    translation_llm_calls = translation_operations

    real_tokens_saved = int(summary_row.real_tokens_saved or 0)
    input_tokens_saved = int(summary_row.input_tokens_saved or 0)
    output_tokens_saved = int(summary_row.output_tokens_saved or 0)
    total_input_tokens = int(summary_row.total_input_tokens or 0)
    total_output_tokens = int(summary_row.total_output_tokens or 0)

    avg_hit_latency = round(float(summary_row.avg_hit_latency), 1) if summary_row.avg_hit_latency is not None else 0.0
    avg_exact_hit_latency = round(float(summary_row.avg_exact_hit_latency), 1) if summary_row.avg_exact_hit_latency is not None else 0.0
    avg_semantic_hit_latency = round(float(summary_row.avg_semantic_hit_latency), 1) if summary_row.avg_semantic_hit_latency is not None else 0.0
    avg_miss_latency = round(float(summary_row.avg_miss_latency), 1) if summary_row.avg_miss_latency is not None else 0.0
    avg_overall_latency = round(float(summary_row.avg_overall_latency), 1) if summary_row.avg_overall_latency is not None else 0.0

    def _round_pct(val: Any) -> float:
        return round(float(val), 1) if val is not None else 0.0

    p50_all, p95_all, p99_all = _round_pct(summary_row.p50_all), _round_pct(summary_row.p95_all), _round_pct(summary_row.p99_all)
    p50_hit, p95_hit, p99_hit = _round_pct(summary_row.p50_hit), _round_pct(summary_row.p95_hit), _round_pct(summary_row.p99_hit)
    p50_miss, p95_miss, p99_miss = _round_pct(summary_row.p50_miss), _round_pct(summary_row.p95_miss), _round_pct(summary_row.p99_miss)

    # SQL-aggregated model usage and token counts
    model_rows = (
        await db.execute(
            select(
                CacheTelemetry.provider.label("provider"),
                CacheTelemetry.model.label("model"),
                func.count().label("requests"),
                func.count().filter(is_hit_cond).label("hits"),
                func.count().filter(is_miss_cond).label("misses"),
                func.coalesce(func.sum(func.coalesce(CacheTelemetry.input_tokens, 0)), 0).label("in_tok"),
                func.coalesce(func.sum(func.coalesce(CacheTelemetry.output_tokens, 0)), 0).label("out_tok"),
                func.coalesce(func.sum(func.coalesce(CacheTelemetry.tokens_saved, 0)), 0).label("saved"),
                func.avg(CacheTelemetry.total_latency_ms).label("avg_latency_ms"),
            )
            .where(*telemetry_where)
            .group_by(CacheTelemetry.provider, CacheTelemetry.model)
            .order_by(func.count().desc())
        )
    ).all()

    model_usage: list[ModelUsageStat] = []
    for row in model_rows:
        in_tok = int(row.in_tok or 0)
        out_tok = int(row.out_tok or 0)
        model_usage.append(
            ModelUsageStat(
                provider=row.provider,
                model=row.model,
                requests=int(row.requests or 0),
                hits=int(row.hits or 0),
                misses=int(row.misses or 0),
                input_tokens=in_tok,
                output_tokens=out_tok,
                total_tokens=in_tok + out_tok,
                tokens_saved=int(row.saved or 0),
                avg_latency_ms=round(float(row.avg_latency_ms), 1) if row.avg_latency_ms is not None else 0.0,
            )
        )

    # SQL-aggregated time-series trends via DATE_TRUNC
    distinct_days_count = int(summary_row.distinct_days_count or 0)
    bucket_unit = "hour" if distinct_days_count <= 3 else "day"
    bucket_fmt = "%Y-%m-%d %H:00" if distinct_days_count <= 3 else "%Y-%m-%d"
    bucket_col = func.date_trunc(bucket_unit, local_ts).label("bucket_dt")

    trend_rows = (
        await db.execute(
            select(
                bucket_col,
                CacheTelemetry.model.label("model"),
                func.count().label("requests"),
                func.count().filter(is_hit_cond).label("hits"),
                func.count().filter(is_miss_cond).label("misses"),
                func.count().filter(CacheTelemetry.cache_status == "exact_hit").label("exact_hits"),
                func.count().filter(CacheTelemetry.cache_status == "semantic_hit").label("semantic_hits"),
                func.coalesce(func.sum(func.coalesce(CacheTelemetry.tokens_saved, 0)), 0).label("tokens_saved"),
                func.coalesce(func.sum(func.coalesce(CacheTelemetry.input_tokens, 0)).filter(is_hit_cond), 0).label("in_tokens_saved"),
                func.coalesce(func.sum(func.coalesce(CacheTelemetry.output_tokens, 0)).filter(is_hit_cond), 0).label("out_tokens_saved"),
                func.coalesce(func.sum(func.coalesce(CacheTelemetry.input_tokens, 0)), 0).label("total_in_tokens"),
                func.coalesce(func.sum(func.coalesce(CacheTelemetry.output_tokens, 0)), 0).label("total_out_tokens"),
                func.coalesce(func.sum(CacheTelemetry.total_latency_ms), 0).label("sum_latency"),
                func.count(CacheTelemetry.total_latency_ms).label("cnt_latency"),
            )
            .where(*telemetry_where)
            .group_by(bucket_col, CacheTelemetry.model)
            .order_by(bucket_col.asc())
        )
    ).all()

    trend_agg: dict[str, dict[str, Any]] = {}
    for row in trend_rows:
        day_key = row.bucket_dt.strftime(bucket_fmt)
        bucket = trend_agg.setdefault(
            day_key,
            {
                "hits": 0,
                "misses": 0,
                "exact_hits": 0,
                "semantic_hits": 0,
                "requests": 0,
                "tokens_saved": 0,
                "in_tokens_saved": 0,
                "out_tokens_saved": 0,
                "total_in_tokens": 0,
                "total_out_tokens": 0,
                "sum_latency": 0.0,
                "cnt_latency": 0,
            },
        )
        in_saved = int(row.in_tokens_saved or 0)
        out_saved = int(row.out_tokens_saved or 0)
        bucket["requests"] += int(row.requests or 0)
        bucket["hits"] += int(row.hits or 0)
        bucket["misses"] += int(row.misses or 0)
        bucket["exact_hits"] += int(row.exact_hits or 0)
        bucket["semantic_hits"] += int(row.semantic_hits or 0)
        bucket["tokens_saved"] += int(row.tokens_saved or 0)
        bucket["in_tokens_saved"] += in_saved
        bucket["out_tokens_saved"] += out_saved
        bucket["total_in_tokens"] += int(row.total_in_tokens or 0)
        bucket["total_out_tokens"] += int(row.total_out_tokens or 0)
        bucket["sum_latency"] += float(row.sum_latency or 0.0)
        bucket["cnt_latency"] += int(row.cnt_latency or 0)

    daily_trends = [
        DailyTrendPoint(
            date=day,
            hits=val["hits"],
            misses=val["misses"],
            exact_hits=val["exact_hits"],
            semantic_hits=val["semantic_hits"],
            requests=val["requests"],
            hit_rate_pct=round((val["hits"] / val["requests"] * 100.0), 1) if val["requests"] > 0 else 0.0,
            tokens_saved=val["tokens_saved"],
            input_tokens_saved=val["in_tokens_saved"],
            output_tokens_saved=val["out_tokens_saved"],
            total_input_tokens=val["total_in_tokens"],
            total_output_tokens=val["total_out_tokens"],
            avg_latency_ms=round(val["sum_latency"] / val["cnt_latency"], 1) if val["cnt_latency"] > 0 else 0.0,
        )
        for day, val in sorted(trend_agg.items())
    ]

    # SQL-aggregated latency distribution buckets via CASE ... GROUP BY
    latency_bucket_names = ("0-10ms", "10-50ms", "50-200ms", "200-1000ms", "1000-3000ms", "3000ms+")
    lat_floor = func.floor(CacheTelemetry.total_latency_ms)
    lat_bucket_expr = case(
        ((lat_floor >= 0) & (lat_floor < 10), "0-10ms"),
        ((lat_floor >= 10) & (lat_floor < 50), "10-50ms"),
        ((lat_floor >= 50) & (lat_floor < 200), "50-200ms"),
        ((lat_floor >= 200) & (lat_floor < 1000), "200-1000ms"),
        ((lat_floor >= 1000) & (lat_floor < 3000), "1000-3000ms"),
        (lat_floor >= 3000, "3000ms+"),
        else_=None,
    ).label("lat_bucket")

    lat_bucket_rows = (
        await db.execute(
            select(
                lat_bucket_expr,
                func.count().filter(CacheTelemetry.cache_status == "exact_hit").label("exact_hits"),
                func.count().filter(CacheTelemetry.cache_status == "semantic_hit").label("semantic_hits"),
                func.count().filter(is_miss_cond).label("misses"),
                func.count().label("count"),
            )
            .where(*telemetry_where, CacheTelemetry.total_latency_ms.is_not(None))
            .group_by(lat_bucket_expr)
        )
    ).all()
    lat_bucket_map = {
        row.lat_bucket: {
            "exact_hits": int(row.exact_hits or 0),
            "semantic_hits": int(row.semantic_hits or 0),
            "misses": int(row.misses or 0),
            "count": int(row.count or 0),
        }
        for row in lat_bucket_rows
        if row.lat_bucket is not None
    }
    latency_buckets = [
        LatencyBucketStat(
            bucket=b_name,
            exact_hits=lat_bucket_map.get(b_name, {}).get("exact_hits", 0),
            semantic_hits=lat_bucket_map.get(b_name, {}).get("semantic_hits", 0),
            misses=lat_bucket_map.get(b_name, {}).get("misses", 0),
            count=lat_bucket_map.get(b_name, {}).get("count", 0),
        )
        for b_name in latency_bucket_names
    ]

    recent_activity: list[TelemetryItemResponse] = []
    for t in recent_activity_rows:
        item_resp, is_hit = _build_telemetry_item(t)
        if is_hit:
            item_resp.related_candidates = None
        else:
            item_resp.matched_query = None

        item_resp.semantic_match_insights = _build_semantic_match_insights(
            t, item_resp, similarity_threshold=eff_threshold
        )

        recent_activity.append(item_resp)

    return CacheStatsResponse(
        total_requests=total_requests,
        cache_hits=cache_hits,
        cache_misses=cache_misses,
        hit_rate_pct=hit_rate_pct,
        exact_hits=exact_hits,
        semantic_hits=semantic_hits,
        exact_hit_rate_pct=exact_hit_rate_pct,
        semantic_hit_rate_pct=semantic_hit_rate_pct,
        llm_calls_avoided=cache_hits,
        variant_reused_count=variant_reused_count,
        translation_operations=translation_operations,
        translation_failures=translation_failures,
        avg_translation_latency_ms=avg_translation_latency_ms,
        answer_llm_calls=answer_llm_calls,
        translation_llm_calls=translation_llm_calls,
        real_tokens_saved=real_tokens_saved,
        input_tokens_saved=input_tokens_saved,
        output_tokens_saved=output_tokens_saved,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        avg_hit_latency_ms=avg_hit_latency,
        avg_exact_hit_latency_ms=avg_exact_hit_latency,
        avg_semantic_hit_latency_ms=avg_semantic_hit_latency,
        avg_miss_latency_ms=avg_miss_latency,
        avg_overall_latency_ms=avg_overall_latency,
        p50_latency_ms=p50_all,
        p95_latency_ms=p95_all,
        p99_latency_ms=p99_all,
        p50_hit_latency_ms=p50_hit,
        p95_hit_latency_ms=p95_hit,
        p99_hit_latency_ms=p99_hit,
        p50_miss_latency_ms=p50_miss,
        p95_miss_latency_ms=p95_miss,
        p99_miss_latency_ms=p99_miss,
        total_entries_count=total_entries,
        recent_activity=recent_activity,
        daily_trends=daily_trends,
        model_usage=model_usage,
        latency_buckets=latency_buckets,
        embedding_model_info=EmbeddingModelInfo(
            name=DEFAULT_MODEL_NAME,
            dimensions=DEFAULT_EMBEDDING_DIM,
            status="active",
        ),
    )


@router.get("/settings", response_model=CacheSettingsResponse)
async def get_cache_settings(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> CacheSettingsResponse:
    """Get persisted cache settings for user."""
    row = await db.scalar(select(CacheSettings).where(CacheSettings.owner_id == user.id))
    if row is None:
        return CacheSettingsResponse(
            similarity_threshold=DEFAULT_SIMILARITY_THRESHOLD,
            default_ttl_hours=DEFAULT_CACHE_TTL_HOURS,
        )
    return CacheSettingsResponse(
        similarity_threshold=row.similarity_threshold,
        default_ttl_hours=row.default_ttl_hours,
    )


@router.patch("/settings", response_model=CacheSettingsResponse)
async def update_cache_settings(
    payload: CacheSettingsPayload,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> CacheSettingsResponse:
    """Persist cache settings (similarity threshold, TTL) in PostgreSQL."""
    row = await db.scalar(select(CacheSettings).where(CacheSettings.owner_id == user.id))
    if row is None:
        row = CacheSettings(
            owner_id=user.id,
            similarity_threshold=payload.similarity_threshold,
            default_ttl_hours=payload.default_ttl_hours,
        )
        db.add(row)
    else:
        row.similarity_threshold = payload.similarity_threshold
        row.default_ttl_hours = payload.default_ttl_hours
    await db.commit()
    await db.refresh(row)
    return CacheSettingsResponse(
        similarity_threshold=row.similarity_threshold,
        default_ttl_hours=row.default_ttl_hours,
    )


@router.get("/telemetry/{telemetry_id}/inspect", response_model=TelemetryItemResponse)
async def inspect_telemetry_item(
    telemetry_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> TelemetryItemResponse:
    """Return enriched inspection payload for Exact Hit, Semantic Hit, or Cache Miss."""
    t = await db.scalar(
        select(CacheTelemetry).where(CacheTelemetry.id == telemetry_id, CacheTelemetry.owner_id == user.id)
    )
    if t is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Telemetry record not found")

    user_settings = await db.scalar(
        select(CacheSettings).where(CacheSettings.owner_id == user.id)
    )
    eff_threshold = (
        float(user_settings.similarity_threshold)
        if user_settings is not None
        else DEFAULT_SIMILARITY_THRESHOLD
    )

    item_resp, is_hit = _build_telemetry_item(t)

    now = datetime.now(timezone.utc)
    if is_hit:
        item_resp.related_candidates = None
        if not item_resp.response_preview or not item_resp.matched_query:
            matched_entry: Optional[CacheEntry] = None
            if t.matched_entry_id:
                matched_entry = await db.scalar(
                    select(CacheEntry).where(CacheEntry.id == t.matched_entry_id, CacheEntry.owner_id == user.id)
                )
            if matched_entry is None and t.cache_status == "exact_hit":
                matched_entry = await db.scalar(
                    select(CacheEntry)
                    .where(
                        CacheEntry.owner_id == user.id,
                        func.lower(CacheEntry.query) == (t.query_preview or "").strip().lower(),
                    )
                    .order_by(CacheEntry.created_at.desc())
                    .limit(1)
                )
            if matched_entry is None and t.query_preview:
                q_vec = await EmbeddingService.get_instance().aembed_query(t.query_preview)
                epoch_floor = datetime(1970, 1, 1, tzinfo=timezone.utc)
                target_lang = (t.detected_language or "").strip() or None
                scored_entries = await query_similar_cache_entries(
                    db,
                    user.id,
                    q_vec,
                    now=epoch_floor,
                    min_similarity=0.72,
                    detected_language=target_lang,
                    limit=5,
                )
                if not scored_entries and target_lang:
                    scored_entries = await query_similar_cache_entries(
                        db,
                        user.id,
                        q_vec,
                        now=epoch_floor,
                        min_similarity=0.72,
                        detected_language=None,
                        limit=5,
                    )
                if scored_entries:
                    if t.cache_status == "semantic_hit" and (t.similarity_score or 1.0) < 0.995:
                        q_lower = (t.query_preview or "").strip().lower()
                        non_identical = [(s, e) for s, e in scored_entries if e.query.strip().lower() != q_lower]
                        chosen = non_identical[0][1] if non_identical else scored_entries[0][1]
                    else:
                        chosen = scored_entries[0][1]
                    matched_entry = chosen
            if matched_entry is not None:
                item_resp.matched_entry_id = matched_entry.id
                item_resp.matched_query = item_resp.matched_query or matched_entry.query
                item_resp.response_preview = item_resp.response_preview or matched_entry.response
            else:
                # Original CacheEntry was deleted earlier; recover exact response and query from ChatMessage / history
                q_clean = (t.query_preview or "").strip()
                if q_clean:
                    user_msg_stmt = select(ChatMessage).where(
                        ChatMessage.owner_id == user.id,
                        ChatMessage.role == "user",
                        func.lower(ChatMessage.content) == q_clean.lower(),
                    )
                    if t.conversation_id:
                        user_msg_stmt = user_msg_stmt.where(ChatMessage.conversation_id == t.conversation_id)
                    user_msg = await db.scalar(user_msg_stmt.order_by(ChatMessage.created_at.desc()).limit(1))
                    if user_msg is None:
                        user_msg = await db.scalar(
                            select(ChatMessage)
                            .where(
                                ChatMessage.owner_id == user.id,
                                ChatMessage.role == "user",
                                func.lower(ChatMessage.content) == q_clean.lower(),
                            )
                            .order_by(ChatMessage.created_at.desc())
                            .limit(1)
                        )
                    if user_msg is not None and not item_resp.response_preview:
                        assistant_msg = await db.scalar(
                            select(ChatMessage)
                            .where(
                                ChatMessage.conversation_id == user_msg.conversation_id,
                                ChatMessage.role == "assistant",
                                ChatMessage.created_at >= user_msg.created_at,
                            )
                            .order_by(ChatMessage.created_at.asc())
                            .limit(1)
                        )
                        if assistant_msg is not None:
                            item_resp.response_preview = assistant_msg.content
                    if not item_resp.matched_query and item_resp.response_preview:
                        exact_resp_entry = await db.scalar(
                            select(CacheEntry)
                            .where(
                                CacheEntry.owner_id == user.id,
                                CacheEntry.response == item_resp.response_preview,
                                CacheEntry.created_at <= t.created_at,
                            )
                            .order_by(CacheEntry.created_at.asc())
                            .limit(1)
                        )
                        if exact_resp_entry is not None:
                            item_resp.matched_entry_id = exact_resp_entry.id
                            item_resp.matched_query = exact_resp_entry.query
                    if not item_resp.matched_query:
                        # Search prior misses/user messages for a semantic match >= 0.72
                        prior_misses = list(
                            (
                                await db.scalars(
                                    select(CacheTelemetry)
                                    .where(
                                        CacheTelemetry.owner_id == user.id,
                                        CacheTelemetry.cache_status == "miss",
                                        CacheTelemetry.created_at <= t.created_at,
                                    )
                                    .order_by(CacheTelemetry.created_at.desc())
                                    .limit(50)
                                )
                            ).all()
                        )
                        q_vec = await EmbeddingService.get_instance().aembed_query(q_clean)
                        best_hist_q: Optional[str] = None
                        best_hist_sim = 0.0
                        for pm in prior_misses:
                            pm_q = (pm.query_preview or "").strip()
                            if not pm_q:
                                continue
                            if (t.similarity_score or 1.0) < 0.995 and pm_q.lower() == q_clean.lower():
                                continue
                            sim_val = cosine_similarity(
                                q_vec, await EmbeddingService.get_instance().aembed_query(pm_q)
                            )
                            if sim_val > best_hist_sim:
                                best_hist_sim = sim_val
                                best_hist_q = pm_q
                        if best_hist_q and best_hist_sim >= 0.72:
                            item_resp.matched_query = best_hist_q
                        else:
                            item_resp.matched_query = q_clean
    elif t.cache_status == "miss":
        item_resp.matched_query = None
        if not item_resp.related_candidates and (t.query_preview or "").strip():
            q_text = t.query_preview.strip()
            q_vec = await EmbeddingService.get_instance().aembed_query(q_text)
            scored = await query_similar_cache_entries(
                db,
                user.id,
                q_vec,
                now=now,
                min_similarity=0.28,
                detected_language=None,
                limit=10,
            )
            filtered_scored = [
                (s, e)
                for s, e in scored
                if e.query.strip().lower() != q_text.lower()
            ]
            item_resp.related_candidates = [
                RelatedCacheMatchItem(
                    entry_id=str(e.id),
                    query=e.query,
                    similarity_score=round(float(s), 4),
                    detected_language=e.detected_language,
                    model=e.model,
                    hit_count=int(e.hit_count or 0),
                )
                for s, e in filtered_scored[:3]
            ]
    else:
        item_resp.matched_query = None
        item_resp.related_candidates = None

    item_resp.semantic_match_insights = _build_semantic_match_insights(
        t, item_resp, similarity_threshold=eff_threshold
    )
    return item_resp
