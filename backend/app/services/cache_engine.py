"""Core language-aware exact and semantic cache engine."""

import hashlib
import inspect
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.redis_client import (
    acquire_cache_lock,
    exact_cache_get,
    exact_cache_set,
    release_cache_lock,
)
from app.config.settings import get_settings
from app.guardrails.config.settings import get_guardrails_settings
from app.models.cache import CacheEntry, CacheSettings, CacheTelemetry
from app.services.embedding_service import get_embedding_service
from app.services.intent_validation_service import (
    canonicalize_hinglish_query_for_search,
    extract_validation_entities,
    validate_candidate_intent,
)
from app.services.response_language_resolver import resolve_response_language

logger = logging.getLogger(__name__)
settings = get_settings()

DEFAULT_SIMILARITY_THRESHOLD = 0.82
DEFAULT_BORDERLINE_RECALL_FLOOR = 0.58
DEFAULT_CACHE_TTL_HOURS = 72
SYSTEM_PROMPT_VERSION = "v2-global-lang"

def normalize_query_for_cache(query: str) -> str:
    """Normalize query for deterministic exact cache keys without stripping language context."""
    text = (query or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = text.strip(" \t\r\n.,!?;:")
    return text


_FOLLOWUP_ANAPHORIC_RE = re.compile(
    r"\b(?:"
    r"that|this|these|those|it|its|above|previous|former|latter|"
    r"step\s*\d+|point\s*\d+|option\s*\d+|part\s*\d+|"
    r"iska|iske|iski|ispar|isme|uske|uska|uski|usme|"
    r"continue|elaborate|simplify|summarize|"
    r"aur\s+batao|aur\s+samjhao|example\s+do|udaharan\s+do"
    r")\b",
    re.IGNORECASE,
)

_STANDALONE_SHORT_FOLLOWUP_RE = re.compile(
    r"^(?:why|how\s+so|what\s+about\s+\w+|give\s+(?:me\s+)?an?\s+example|show\s+(?:me\s+)?(?:an?\s+)?(?:example|code)|explain\s+(?:more|again)|tell\s+me\s+more)[\?\!\.\s]*$",
    re.IGNORECASE,
)


def is_context_dependent_followup(query: str) -> bool:
    """Return True when a query relies on prior conversation turns and should bypass global cache."""
    text = (query or "").strip()
    if not text:
        return False
    if _STANDALONE_SHORT_FOLLOWUP_RE.match(text):
        return True
    words = text.split()
    if len(words) <= 8 and _FOLLOWUP_ANAPHORIC_RE.search(text):
        return True
    return False


@dataclass
class CacheLookupResult:
    """Outcome of checking exact and semantic cache layers."""

    hit: bool
    cache_type: str  # 'exact_hit', 'semantic_hit', 'miss'
    response: str | None = None
    similarity_score: float | None = None
    cached_entry_id: uuid.UUID | None = None
    matched_query: str | None = None
    related_candidates: list[dict[str, Any]] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    lookup_latency_ms: int = 0
    detected_language: str = "English"
    requested_language: str = "English"
    effective_response_language: str = "English"
    input_language: str = "English"
    language_policy: str = "default"
    cache_source: str = "LLM API"
    supported: bool = True
    intent: str = "general"
    variant_reused: bool = False
    translation_performed: bool = False
    translation_failed: bool = False
    translation_latency_ms: int = 0
    matched_queries_snapshot: list[dict[str, Any]] = field(default_factory=list)
    rejected_candidates_snapshot: list[dict[str, Any]] = field(default_factory=list)
    validation_explanation: str | None = None


def compute_exact_cache_key(
    owner_id: uuid.UUID,
    provider: str,
    model: str,
    normalized_query: str,
    effective_response_language: str = "English",
    system_prompt_version: str = SYSTEM_PROMPT_VERSION,
    generation_params: str = "default",
    policy_version: str | None = None,
) -> str:
    """Generate deterministic SHA-256 cache key scoped by owner, model, prompt version, policy version, params, and response language."""
    pol_ver = policy_version or get_guardrails_settings().GUARDRAILS_POLICY_VERSION
    lang_slug = effective_response_language.strip().lower().replace(" ", "_")
    raw = (
        f"{owner_id}:{system_prompt_version}:{pol_ver}:{generation_params}:{lang_slug}:{normalized_query}"
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"llm:exact:v1:{owner_id}:{lang_slug}:{digest}"


def compute_config_hash(provider: str, model: str) -> str:
    """Fingerprint model configuration compatibility."""
    raw = f"{provider.lower()}:{model.lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two equal-length embedding vectors via NumPy."""
    a = np.asarray(vec_a, dtype=float)
    b = np.asarray(vec_b, dtype=float)
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom > 0.0 else 0.0


def _is_postgres_session(db: Any) -> bool:
    if not isinstance(db, AsyncSession):
        return False
    bind = getattr(db, "bind", None)
    if bind is None:
        try:
            bind = db.get_bind()
        except Exception:
            bind = None
    return getattr(getattr(bind, "dialect", None), "name", None) == "postgresql"


async def _embed_query(service: Any, query: str) -> list[float]:
    """Use the async embedding API while supporting lightweight sync test doubles."""
    async_method = getattr(service, "aembed_query", None)
    if async_method is not None:
        result = async_method(query)
        if inspect.isawaitable(result):
            return await result
    return service.embed_query(query)


async def query_similar_cache_entries(
    db: AsyncSession,
    owner_id: uuid.UUID,
    query_embedding: list[float],
    *,
    now: datetime,
    min_similarity: float = 0.0,
    detected_language: str | None = None,
    policy_version: str | None = None,
    limit: int = 30,
) -> list[tuple[float, CacheEntry]]:
    """Rank active CacheEntry rows by cosine similarity using native pgvector HNSW in PostgreSQL."""
    active_policy = policy_version or get_guardrails_settings().GUARDRAILS_POLICY_VERSION
    if _is_postgres_session(db):
        qvec = [float(x) for x in query_embedding]
        dist_expr = CacheEntry.query_embedding.cosine_distance(qvec)
        sim_expr = (1.0 - dist_expr).label("sim")
        stmt = (
            select(CacheEntry, sim_expr)
            .where(
                CacheEntry.owner_id == owner_id,
                CacheEntry.status == "active",
                CacheEntry.expires_at > now,
                CacheEntry.policy_version == active_policy,
            )
            .order_by(dist_expr.asc())
            .limit(int(limit))
        )
        if detected_language is not None:
            stmt = stmt.where(CacheEntry.detected_language == detected_language)
        rows = (await db.execute(stmt)).all()
        ranked = [
            (float(sim), entry)
            for entry, sim in rows
            if sim is not None and float(sim) >= float(min_similarity)
        ]
        return ranked

    stmt = select(CacheEntry).where(
        CacheEntry.owner_id == owner_id,
        CacheEntry.status == "active",
        CacheEntry.expires_at > now,
        CacheEntry.policy_version == active_policy,
    )
    if detected_language is not None:
        stmt = stmt.where(CacheEntry.detected_language == detected_language)
    candidates = list((await db.scalars(stmt)).all())
    scored: list[tuple[float, CacheEntry]] = []
    for candidate in candidates:
        sim = cosine_similarity(query_embedding, candidate.query_embedding)
        if sim >= min_similarity:
            scored.append((sim, candidate))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[:limit]


class SemanticCacheEngine:
    """Language-aware exact + semantic cache engine with English-by-default policy and no auto-translation."""

    def __init__(self, db: AsyncSession, owner_id: uuid.UUID):
        self.db = db
        self.owner_id = owner_id
        self.embedding_service = get_embedding_service()

    async def _get_user_settings(self) -> tuple[float, int]:
        """Fetch per-user similarity threshold and TTL from DB, with safe defaults."""
        try:
            user_settings = await self.db.scalar(
                select(CacheSettings).where(CacheSettings.owner_id == self.owner_id)
            )
            if user_settings is not None:
                return float(user_settings.similarity_threshold), int(user_settings.default_ttl_hours)
        except Exception as exc:
            logger.debug("Using default cache settings: %s", exc)
        return DEFAULT_SIMILARITY_THRESHOLD, DEFAULT_CACHE_TTL_HOURS

    async def lookup(
        self,
        query: str,
        provider: str,
        model: str,
        *,
        conversation_language_preference: str | None = None,
        use_llm_judge: bool = True,
        system_prompt_version: str = SYSTEM_PROMPT_VERSION,
        generation_params: str = "default",
    ) -> CacheLookupResult:
        """Execute exact lookup, language-filtered semantic lookup, and intent validation."""
        t0 = time.perf_counter()

        resolution = resolve_response_language(
            query,
            conversation_language_preference=conversation_language_preference,
        )
        eff_lang = resolution.effective_response_language
        clean_query = resolution.clean_query_for_cache
        normalized = normalize_query_for_cache(clean_query)

        if not normalized:
            return CacheLookupResult(
                hit=False,
                cache_type="miss",
                similarity_score=0.0,
                lookup_latency_ms=max(1, int((time.perf_counter() - t0) * 1000)),
                detected_language=resolution.input_language,
                requested_language=eff_lang,
                effective_response_language=eff_lang,
                input_language=resolution.input_language,
                language_policy=resolution.language_policy,
                cache_source="LLM API",
                supported=True,
            )

        # 1. L1 exact cache lookup
        exact_key = compute_exact_cache_key(
            self.owner_id,
            provider,
            model,
            normalized,
            effective_response_language=eff_lang,
            system_prompt_version=system_prompt_version,
            generation_params=generation_params,
        )
        try:
            cached_raw = await exact_cache_get(exact_key)
            if cached_raw:
                data = json.loads(cached_raw)
                stored_lang = data.get("response_language")
                orig_response = data.get("response")
                # Legacy/mismatch guard: only return if stored response_language matches effective_response_language
                if isinstance(orig_response, str) and orig_response and stored_lang == eff_lang:
                    entry_id = uuid.UUID(data["entry_id"]) if data.get("entry_id") else None
                    if entry_id is not None:
                        try:
                            db_entry = await self.db.scalar(
                                select(CacheEntry).where(CacheEntry.id == entry_id)
                            )
                            if db_entry is not None:
                                db_entry.hit_count += 1
                                db_entry.last_hit_at = func.now()
                                await self.db.commit()
                        except Exception as exc:
                            logger.debug("Non-fatal exact hit DB stat update error: %s", exc)

                    lookup_latency = max(1, int((time.perf_counter() - t0) * 1000))
                    return CacheLookupResult(
                        hit=True,
                        cache_type="exact_hit",
                        response=orig_response,
                        similarity_score=1.0,
                        cached_entry_id=entry_id,
                        matched_query=str(data.get("query") or query),
                        input_tokens=int(data.get("input_tokens", 0)),
                        output_tokens=int(data.get("output_tokens", 0)),
                        lookup_latency_ms=lookup_latency,
                        detected_language=resolution.input_language,
                        requested_language=eff_lang,
                        effective_response_language=eff_lang,
                        input_language=resolution.input_language,
                        language_policy=resolution.language_policy,
                        cache_source="Redis Exact Cache",
                        supported=True,
                    )
        except Exception as exc:
            logger.warning("Exact cache lookup failed gracefully: %s", exc)

        # 2. L2 SEMANTIC VECTOR RETRIEVAL (SQL-ranked across 100% of active entries for effective_response_language)
        threshold, _ = await self._get_user_settings()
        query_embedding = await _embed_query(self.embedding_service, clean_query)

        now = datetime.now(timezone.utc)
        ranked_candidates = await query_similar_cache_entries(
            self.db,
            self.owner_id,
            query_embedding,
            now=now,
            min_similarity=0.0,
            detected_language=eff_lang,
            limit=30,
        )

        scored_candidates: list[tuple[float, CacheEntry]] = []
        miss_candidates_map: dict[uuid.UUID, tuple[float, CacheEntry]] = {}
        best_raw_similarity = 0.0
        recall_floor = min(threshold, DEFAULT_BORDERLINE_RECALL_FLOOR) if use_llm_judge else threshold
        relevance_floor = 0.28

        if (
            resolution.input_language == "Hinglish"
            and use_llm_judge
            and max((s for s, _ in ranked_candidates), default=0.0) < threshold
        ):
            pivot_en = await canonicalize_hinglish_query_for_search(
                clean_query,
                provider=provider,
                model=model,
            )
            if pivot_en and pivot_en.lower() != clean_query.lower():
                pivot_embedding = await _embed_query(self.embedding_service, pivot_en)
                pivot_candidates = await query_similar_cache_entries(
                    self.db,
                    self.owner_id,
                    pivot_embedding,
                    now=now,
                    min_similarity=0.0,
                    detected_language=eff_lang,
                    limit=30,
                )
                merged: dict[uuid.UUID, tuple[float, CacheEntry]] = {
                    cand.id: (sim, cand) for sim, cand in ranked_candidates
                }
                for p_sim, p_cand in pivot_candidates:
                    prev = merged.get(p_cand.id)
                    if prev is None or p_sim > prev[0]:
                        merged[p_cand.id] = (p_sim, p_cand)
                ranked_candidates = sorted(merged.values(), key=lambda item: item[0], reverse=True)

        for sim, candidate in ranked_candidates:
            if sim > best_raw_similarity:
                best_raw_similarity = sim
            if sim >= recall_floor:
                scored_candidates.append((sim, candidate))
            if sim >= relevance_floor and candidate.query.strip().lower() != query.strip().lower():
                miss_candidates_map[candidate.id] = (sim, candidate)

        scored_candidates.sort(key=lambda item: item[0], reverse=True)

        # 3. INTENT & COMPATIBILITY VALIDATION ON CANDIDATES, THEN SELECT TOP 3 COMPATIBLE MATCHES
        accepted_matches: list[tuple[float, CacheEntry, Any]] = []
        rejected_candidates: list[dict[str, Any]] = []
        max_stage2_candidates = 10

        def _candidate_snapshot(
            cand: CacheEntry,
            score: float,
            *,
            compatible: bool,
            confidence: float,
            summary: str,
            reason: str,
            rank: int | None = None,
            selected: bool | None = None,
        ) -> dict[str, Any]:
            item: dict[str, Any] = {
                "cache_entry_id": str(cand.id),
                "previous_query": cand.query,
                "similarity_score": round(float(score), 4),
                "intent_compatible": compatible,
                "intent_status": "Compatible" if compatible else "Incompatible",
                "confidence": round(float(confidence), 4),
                "intent_summary": summary,
                "reason": reason,
                "detected_language": cand.detected_language,
                "model": cand.model,
            }
            if rank is not None:
                item["rank"] = rank
            if selected is not None:
                item["selected"] = selected
            return item

        for sim, candidate in scored_candidates[:max_stage2_candidates]:
            # Extra defense-in-depth check against legacy or mismatched language metadata
            if candidate.detected_language != eff_lang:
                rejected_candidates.append(_candidate_snapshot(
                    candidate, sim, compatible=False, confidence=1.0,
                    summary="Language mismatch",
                    reason=f"Candidate response language ({candidate.detected_language}) differs from effective response language ({eff_lang}).",
                ))
                continue

            validation = await validate_candidate_intent(
                clean_query,
                candidate.query,
                sim,
                provider=provider,
                model=model,
                use_llm_judge=use_llm_judge,
                similarity_threshold=threshold,
            )
            if not validation.is_valid:
                rejected_candidates.append(_candidate_snapshot(
                    candidate, sim, compatible=False, confidence=validation.confidence,
                    summary=validation.intent_summary, reason=validation.reason,
                ))
                continue

            accepted_matches.append((sim, candidate, validation))
            if len(accepted_matches) >= 1:
                break

        if accepted_matches:
            # Rank accepted compatible matches by actual cosine similarity and select the top 1 match
            accepted_matches.sort(key=lambda item: item[0], reverse=True)
            top_accepted = accepted_matches[:1]
            best_sim, selected_candidate, best_validation = top_accepted[0]

            selected_candidate.hit_count += 1
            selected_candidate.last_hit_at = func.now()
            await self.db.commit()

            matched_snapshot = [
                _candidate_snapshot(
                    cand, score, compatible=True, confidence=val.confidence,
                    summary=val.intent_summary, reason=val.reason, rank=idx, selected=idx == 1,
                )
                for idx, (score, cand, val) in enumerate(top_accepted, start=1)
            ]

            lookup_latency = max(1, int((time.perf_counter() - t0) * 1000))
            return CacheLookupResult(
                hit=True,
                cache_type="semantic_hit",
                response=selected_candidate.response,
                similarity_score=float(best_sim),
                cached_entry_id=selected_candidate.id,
                matched_query=selected_candidate.query,
                input_tokens=selected_candidate.input_tokens,
                output_tokens=selected_candidate.output_tokens,
                lookup_latency_ms=lookup_latency,
                detected_language=resolution.input_language,
                requested_language=eff_lang,
                effective_response_language=eff_lang,
                input_language=resolution.input_language,
                language_policy=resolution.language_policy,
                cache_source="Semantic Cache",
                supported=True,
                matched_queries_snapshot=matched_snapshot,
                rejected_candidates_snapshot=rejected_candidates,
                validation_explanation=best_validation.reason,
            )

        top_related = sorted(miss_candidates_map.values(), key=lambda item: item[0], reverse=True)[:1]
        related_payload = [
            {
                "entry_id": str(getattr(c, "id", "")),
                "query": getattr(c, "query", ""),
                "similarity_score": round(float(s), 4),
                "detected_language": getattr(c, "detected_language", eff_lang),
                "model": getattr(c, "model", model),
                "hit_count": int(getattr(c, "hit_count", 0) or 0),
            }
            for s, c in top_related
        ]

        miss_explanation = (
            rejected_candidates[0]["reason"]
            if rejected_candidates
            else "No cached semantic candidates met the vector similarity threshold."
        )

        lookup_latency = max(1, int((time.perf_counter() - t0) * 1000))
        return CacheLookupResult(
            hit=False,
            cache_type="miss",
            similarity_score=float(best_raw_similarity) if best_raw_similarity > 0 else None,
            related_candidates=related_payload,
            lookup_latency_ms=lookup_latency,
            detected_language=resolution.input_language,
            requested_language=eff_lang,
            effective_response_language=eff_lang,
            input_language=resolution.input_language,
            language_policy=resolution.language_policy,
            cache_source="LLM API",
            supported=True,
            matched_queries_snapshot=[],
            rejected_candidates_snapshot=rejected_candidates,
            validation_explanation=miss_explanation,
        )

    async def store(
        self,
        query: str,
        response: str,
        provider: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        ttl_hours: int | None = None,
        *,
        conversation_language_preference: str | None = None,
        effective_response_language: str | None = None,
        language_policy: str | None = None,
        system_prompt_version: str = SYSTEM_PROMPT_VERSION,
        generation_params: str = "default",
    ) -> CacheEntry:
        """Store a validated LLM response in PostgreSQL and the exact cache."""
        resolution = resolve_response_language(
            query,
            conversation_language_preference=conversation_language_preference,
        )
        eff_lang = effective_response_language or resolution.effective_response_language
        eff_policy = language_policy or resolution.language_policy
        clean_query = resolution.clean_query_for_cache
        normalized = normalize_query_for_cache(clean_query)
        embedding = await _embed_query(self.embedding_service, clean_query or query)
        config_hash = compute_config_hash(provider, model)

        _, default_ttl_hours = await self._get_user_settings()
        effective_ttl_hours = ttl_hours if ttl_hours is not None else default_ttl_hours
        ttl_seconds = max(60, int(effective_ttl_hours) * 3600)

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl_seconds)

        exact_key = compute_exact_cache_key(
            self.owner_id,
            provider,
            model,
            normalized,
            effective_response_language=eff_lang,
            system_prompt_version=system_prompt_version,
            generation_params=generation_params,
        )
        lock_key = f"lock:{exact_key}"
        lock_acquired = await acquire_cache_lock(lock_key, ttl_seconds=10)

        try:
            entry = CacheEntry(
                owner_id=self.owner_id,
                query=query,
                normalized_query=normalized,
                query_embedding=embedding,
                embedding_dim=len(embedding),
                embedding_model=self.embedding_service.model_name,
                response=response,
                detected_language=eff_lang,
                intent="semantic",
                depth_scope="standard",
                critical_entities=extract_validation_entities(clean_query),
                provider=provider,
                model=model,
                config_hash=config_hash,
                policy_version=get_guardrails_settings().GUARDRAILS_POLICY_VERSION,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                hit_count=0,
                status="active",
                created_at=now,
                expires_at=expires_at,
            )
            self.db.add(entry)
            await self.db.commit()
            await self.db.refresh(entry)

            try:
                payload = {
                    "entry_id": str(entry.id),
                    "query": query,
                    "response": response,
                    "response_language": eff_lang,
                    "input_language": resolution.input_language,
                    "language_policy": eff_policy,
                    "policy_version": get_guardrails_settings().GUARDRAILS_POLICY_VERSION,
                    "provider": provider,
                    "model": model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "created_at": now.isoformat(),
                }
                await exact_cache_set(exact_key, json.dumps(payload), ex_seconds=ttl_seconds)
            except Exception as exc:
                logger.warning("Failed to populate exact Redis cache: %s", exc)

            return entry
        finally:
            if lock_acquired:
                await release_cache_lock(lock_key)

    async def record_telemetry(
        self,
        query: str,
        cache_status: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        lookup_latency_ms: int,
        total_latency_ms: int,
        conversation_id: uuid.UUID | None = None,
        similarity_score: float | None = None,
        detected_language: str | None = None,
        requested_language: str | None = None,
        variant_reused: bool = False,
        translation_performed: bool = False,
        translation_failed: bool = False,
        translation_latency_ms: int = 0,
        matched_entry_id: uuid.UUID | None = None,
        matched_query: str | None = None,
        response_preview: str | None = None,
        related_candidates: list[dict[str, Any]] | None = None,
        current_query: str | None = None,
        matched_queries_snapshot: list[dict[str, Any]] | None = None,
        rejected_candidates_snapshot: list[dict[str, Any]] | None = None,
        returned_response_snapshot: str | None = None,
        validation_explanation: str | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Save real request telemetry."""
        if detected_language is None or requested_language is None:
            res = resolve_response_language(query)
            detected_language = detected_language or res.input_language
            requested_language = requested_language or res.effective_response_language

        is_hit = cache_status in ("exact_hit", "semantic_hit")
        no_llm = is_hit
        tokens_saved = (input_tokens + output_tokens) if is_hit else 0
        llm_latency_ms = 0 if no_llm else max(0, total_latency_ms - lookup_latency_ms)
        latency_saved_ms = max(0, 1800 - lookup_latency_ms) if is_hit else 0

        effective_response_preview = response_preview
        if cache_status == "error" and not effective_response_preview and (error_type or error_message):
            effective_response_preview = f"[{error_type}] {error_message}" if error_type else error_message

        telemetry = CacheTelemetry(
            owner_id=self.owner_id,
            conversation_id=conversation_id,
            query_preview=query[:250],
            detected_language=detected_language[:80],
            requested_language=requested_language[:80],
            cache_status=cache_status,
            similarity_score=similarity_score,
            matched_entry_id=matched_entry_id,
            matched_query=matched_query if is_hit else None,
            response_preview=effective_response_preview,
            related_candidates=related_candidates if cache_status == "miss" else None,
            current_query=current_query or query,
            matched_queries_snapshot=matched_queries_snapshot if cache_status == "semantic_hit" else None,
            rejected_candidates_snapshot=rejected_candidates_snapshot if cache_status in ("semantic_hit", "miss") else None,
            returned_response_snapshot=returned_response_snapshot if cache_status == "semantic_hit" else None,
            validation_explanation=validation_explanation if cache_status in ("semantic_hit", "miss") else None,
            variant_reused=variant_reused,
            translation_performed=translation_performed,
            translation_failed=translation_failed,
            translation_latency_ms=translation_latency_ms,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            tokens_saved=tokens_saved,
            total_latency_ms=total_latency_ms,
            cache_lookup_latency_ms=lookup_latency_ms,
            llm_latency_ms=llm_latency_ms,
            latency_saved_ms=latency_saved_ms,
        )
        self.db.add(telemetry)
        await self.db.commit()
