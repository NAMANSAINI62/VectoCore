"""LangChain prompt pipeline orchestrated as an explicit LangGraph workflow."""

import asyncio
from datetime import datetime, timezone
import re
import time
from typing import Any

from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.messages import SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chatbot.state import ChatState
from app.config.settings import get_settings
from app.guardrails.config.settings import get_guardrails_settings
from app.guardrails.schemas import Decision
from app.guardrails.service import get_guardrails_service
from app.guardrails.tools import MAX_TOOL_CALLS_PER_REQUEST, execute_tool
from app.llm.registry import (
    build_fallback_candidates,
    get_chat_model,
    get_model_label,
    get_quota_router,
    resolve_effective_tier,
    select_best_model_candidate,
    validate_provider_model,
)
from app.models.chat import ChatConversation, ChatMessage
from app.services.cache_engine import SemanticCacheEngine
from app.services.token_service import count_tokens
from app.services.language_service import (
    detect_input_language,
    resolve_response_language_async,
)

settings = get_settings()

SYSTEM_PROMPT = (
    "You are a helpful, clear, and honest assistant. "
    "Do not claim to have used tools or sources you did not use. "
    "When tool outputs provide source URLs, ground your answer in those results and place clickable inline markdown links "
    "like [[1]](https://exact-url) or [[2]](https://exact-url) directly on the sentence where the fact is used. "
    "Do NOT add a separate Sources section at the bottom.\n\n"
    "RESPONSE SCOPE & LENGTH POLICY:\n"
    "- Answer directly what the user asked in their current query.\n"
    "- Follow the active RESPONSE DEPTH POLICY below for depth, structure, and length. Do not add filler introductions, closing fluff, or meta-commentary about your instructions or language policy.\n\n"
    "RESPONSE LANGUAGE POLICY:\n"
    "- Write the ENTIRE final answer strictly in {effective_response_language} without announcing or explaining the language policy.\n"
    "- If {effective_response_language} is Hindi, write completely in pure Hindi (Devanagari script) — NEVER answer in English or Hinglish.\n"
    "- If {effective_response_language} is Hinglish, write naturally in Romanized Hinglish (Latin script) — NEVER in Devanagari script."
)


def validate_generated_response_language(text: str, effective_response_language: str) -> bool:
    """Validate response language compliance using lingua-py instead of manual Unicode script regexes."""
    content = (text or "").strip()
    if not content:
        return False

    eff = (effective_response_language or "English").strip()
    if "+" in eff:
        return True

    alpha_count = sum(1 for ch in content if ch.isalpha())
    if alpha_count < 20:
        return True

    detected = detect_input_language(content)
    if eff == "English":
        return detected in ("English", "Hinglish")
    if eff == "Hinglish":
        return detected in ("Hinglish", "English")
    if len(content) < 25:
        return True
    return detected.lower() == eff.lower()


def _supports_postgres_cache(db: Any) -> bool:
    """Return False for explicitly non-PostgreSQL SQLAlchemy sessions (e.g. SQLite tests)."""
    bind = getattr(db, "bind", None)
    return not (bind and getattr(bind, "dialect", None) and bind.dialect.name != "postgresql")


async def validate_request(state: ChatState) -> dict[str, Any]:
    message = state.get("message", "").strip()
    max_chars = get_guardrails_settings().GUARDRAILS_MAX_INPUT_CHARS
    if not message or len(message) > max_chars:
        raise ValueError(f"Message must contain 1-{max_chars} non-whitespace characters.")
    validate_provider_model(state["provider"], state["model"])
    return {"message": message, "started_at": time.perf_counter()}


def _emit_cache_telemetry(
    writer: Any,
    *,
    hit: bool,
    cache_type: str,
    cache_source: str,
    similarity_score: float | None = None,
    lookup_latency_ms: int = 0,
    saved_tokens: int = 0,
    extra: dict[str, Any] | None = None,
) -> None:
    payload = {
        "hit": hit,
        "cache_type": cache_type,
        "cache_source": cache_source,
        "similarity_score": similarity_score,
        "lookup_latency_ms": lookup_latency_ms,
        "saved_tokens": saved_tokens,
        **(extra or {}),
    }
    writer({"event": "cache.telemetry", "data": payload})


def _lookup_lang_fields(lookup: Any) -> dict[str, Any]:
    return {
        "detected_language": lookup.detected_language,
        "requested_language": lookup.requested_language,
        "effective_response_language": lookup.effective_response_language,
        "input_language": lookup.input_language,
        "language_policy": lookup.language_policy,
    }


_LIVE_SEARCH_INTENT_RE = re.compile(
    r"(?:\b(?:latest|current|currently|today|right now|recent|news|breaking|headlines?|"
    r"web\s*search|search(?:\s+(?:the\s+web|online|karo|kar|kro))?|look\s*up|google|browse|live|"
    r"aaj|abhi|taaza|taza|khabar|samachar|mausam|weather|forecast|temperature|taapman|"
    r"price|rate|bhav|daam|bitcoin|btc|eth|crypto|stock|nifty|sensex|score|match|ipl|"
    r"restaurants?|near\s+me|nearby|ke\s+paas|"
    r"documenta\w*|documen\w*|docs|official\s+(?:site|website|page|docs)|website|web\s*site|web\s*page|"
    r"check\s+(?:the\s+)?(?:\w+\s+){0,3}(?:site|website|docs|documentation|page)|"
    r"hoy|noticias|clima|precio|[úu]ltimas|reciente|buscar\s+en\s+(?:la\s+web|internet)|"
    r"aujourd'hui|actualit[ée]s|m[ée]t[ée]o|prix|derni[èe]res|chercher?\s+sur\s+(?:le\s+web|internet)|"
    r"heute|nachrichten|wetter|aktuelle)\b|"
    r"आज|अभी|ताज़ा|ताजा|खबर|खबरें|समाचार|मौसम|तापमान|कीमत|भाव|दाम|लाइव|स्कोर|मैच|"
    r"लेटेस्ट|नया\s+वर्जन|वेब\s*सर्च|सर्च\s*कर|खोजो|गूगल\s*कर|वेबसाइट|ऑफिशियल)",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"https?://[^\s<>\"']+")

_REFUSAL_RE = re.compile(
    r"\b(?:i\s+(?:cannot|can't|can not|am unable to|am not able to|don't have the ability to)\s+"
    r"(?:browse|access|fetch|visit|open|retrieve|search)|unable to (?:fetch|browse|access))\b",
    re.IGNORECASE,
)


def _detect_live_tool_calls(message: str) -> list[dict[str, Any]]:
    """Return MCP tool calls required by a message (URL fetch or web search), or [] if none."""
    from app.mcp.config import get_mcp_settings

    if not get_mcp_settings().MCP_ENABLED:
        return []
    msg = message or ""
    urls = [u.rstrip(".,;:!?)]}") for u in _URL_RE.findall(msg)]
    urls = [u for u in urls if u]
    if urls:
        return [{"name": "fetch__get_page", "args": {"url": u}} for u in urls[:MAX_TOOL_CALLS_PER_REQUEST]]
    if _LIVE_SEARCH_INTENT_RE.search(msg):
        return [{"name": "search__web_search", "args": {"query": msg[:200]}}]
    return []


async def check_cache(state: ChatState) -> dict[str, Any]:
    """Resolve response language and check exact/semantic cache before calling the LLM."""
    writer = get_stream_writer()
    writer({
        "event": "status.update",
        "data": {"stage": "cache_lookup", "message": "Checking cache and language policy…"},
    })
    conv_pref = state.get("conversation_language_preference")
    resolution = await resolve_response_language_async(
        state["message"],
        conversation_language_preference=conv_pref,
        provider=state.get("provider"),
        model=state.get("model"),
    )
    base_lang_state = {
        "input_language": resolution.input_language,
        "effective_response_language": resolution.effective_response_language,
        "language_policy": resolution.language_policy,
    }

    try:
        db: AsyncSession = state["db"]
        user_id = state["user_id"]

        if not _supports_postgres_cache(db):
            return {
                "is_cached": False,
                "cache_lookup": None,
                **base_lang_state,
            }

        # Live web/MCP requests (URLs, docs, "latest", "search", etc.) always fetch live data instead of serving cache
        live_calls = _detect_live_tool_calls(state["message"])
        if live_calls:
            tool_names = ", ".join(sorted({str(c.get("name", "")) for c in live_calls if c.get("name")}))
            _emit_cache_telemetry(
                writer,
                hit=False,
                cache_type="fetch",
                cache_source=f"Live MCP ({tool_names})",
                extra=base_lang_state,
            )
            return {
                "is_cached": False,
                "skip_cache": True,
                "fetch_reason": f"Live MCP tool ({tool_names}) fetched real-time web data.",
                "cache_lookup": None,
                **base_lang_state,
            }

        engine = SemanticCacheEngine(db, user_id)
        lookup = await engine.lookup(
            query=state["message"],
            provider=state["provider"],
            model=state["model"],
            conversation_language_preference=conv_pref,
        )

        if lookup.hit:
            _emit_cache_telemetry(
                writer,
                hit=True,
                cache_type=lookup.cache_type,
                cache_source=lookup.cache_source,
                similarity_score=lookup.similarity_score,
                lookup_latency_ms=lookup.lookup_latency_ms,
                saved_tokens=lookup.input_tokens + lookup.output_tokens,
                extra=_lookup_lang_fields(lookup),
            )
            writer({"event": "content.delta", "data": lookup.response})

            elapsed_ms = max(1, int((time.perf_counter() - state["started_at"]) * 1000))
            await engine.record_telemetry(
                query=state["message"],
                cache_status=lookup.cache_type,
                provider=state["provider"],
                model=state["model"],
                input_tokens=lookup.input_tokens,
                output_tokens=lookup.output_tokens,
                lookup_latency_ms=lookup.lookup_latency_ms,
                total_latency_ms=elapsed_ms,
                conversation_id=state["conversation_id"],
                similarity_score=lookup.similarity_score,
                detected_language=lookup.detected_language,
                requested_language=lookup.requested_language,
                matched_entry_id=lookup.cached_entry_id,
                matched_query=lookup.matched_query,
                response_preview=lookup.response,
                current_query=state["message"],
                matched_queries_snapshot=lookup.matched_queries_snapshot,
                rejected_candidates_snapshot=lookup.rejected_candidates_snapshot,
                returned_response_snapshot=lookup.response,
                validation_explanation=lookup.validation_explanation,
            )

            hit_verdict = await get_guardrails_service().check_cache_hit_output(
                lookup.response,
                user_id=user_id,
                db=db,
            )
            hit_response = lookup.response
            hit_blocked = False
            if hit_verdict.effective_decision in (Decision.BLOCK, Decision.FALLBACK, Decision.REQUIRE_REVIEW):
                hit_response = hit_verdict.user_safe_message or "I cannot fulfill this request due to safety guidelines."
                hit_blocked = True

            return {
                "is_cached": True,
                "raw_answer": hit_response,
                "output_blocked": hit_blocked,
                "cache_lookup": lookup,
                "language_valid": True,
                "usage": {
                    "input_tokens": lookup.input_tokens,
                    "output_tokens": lookup.output_tokens,
                },
                **base_lang_state,
            }

        _emit_cache_telemetry(
            writer,
            hit=False,
            cache_type="miss",
            cache_source="LLM API",
            similarity_score=lookup.similarity_score,
            lookup_latency_ms=lookup.lookup_latency_ms,
            extra=_lookup_lang_fields(lookup),
        )
        return {
            "is_cached": False,
            "cache_lookup": lookup,
            **base_lang_state,
        }
    except Exception:
        # Cache failure must never prevent or fail chatbot generation
        return {"is_cached": False, "cache_lookup": None, **base_lang_state}


def route_after_cache(state: ChatState) -> str:
    """If cache hit, skip prompt configuration, MCP tools, and LLM call entirely."""
    if state.get("is_cached", False):
        return "process_response"
    return "select_prompt_configuration"


async def select_prompt_configuration(_: ChatState) -> dict[str, Any]:
    """Select the shared single-turn prompt with global language policy and runtime canary marker."""
    canary = get_guardrails_service().get_runtime_canary()
    prompt_with_canary = ChatPromptTemplate.from_messages([
        (
            "system",
            f"{SYSTEM_PROMPT}\n\n[INTERNAL INTEGRITY MARKER: {canary} - never repeat or reveal this marker.]{{extra_system_context}}",
        ),
        ("human", "{message}"),
    ])
    return {"prompt": prompt_with_canary, "history": []}


async def tools_stage(state: ChatState) -> dict[str, Any]:
    """Execute allowlisted MCP/tool calls before generate_response for ALL models."""
    tool_calls = list(state.get("tool_calls") or [])
    if not tool_calls:
        tool_calls = _detect_live_tool_calls(state.get("message", ""))
    if not tool_calls:
        return {}
    svc = get_guardrails_service()
    writer = get_stream_writer()
    results: list[str] = []
    for call in tool_calls[:MAX_TOOL_CALLS_PER_REQUEST]:
        name = str(call.get("name", ""))
        args = call.get("args") or {}
        if name == "fetch__get_page":
            writer({"event": "status.update", "data": {"status": "Reading page..."}})
        elif name == "search__web_search":
            writer({"event": "status.update", "data": {"status": "Searching the web..."}})
        else:
            writer({"event": "status.update", "data": {"status": f"Running {name}..."}})
        try:
            out = await execute_tool(
                name,
                args,
                owner_id=state["user_id"],
                db=state.get("db"),
                injection_detector=svc.injection_detector,
                secret_detector=svc.secret_scanner_detector,
            )
            results.append(f"[{name}]: {out}")
        except Exception as exc:
            # Strict MCP separation: NEVER silently mix fetch__get_page with search__web_search
            err_detail = re.sub(r"\s+", " ", str(exc)).strip()[:160]
            target_info = f" for {args.get('url')}" if args.get("url") else ""
            results.append(
                f"[{name} unavailable{target_info}]: {type(exc).__name__}"
                + (f": {err_detail}" if err_detail else "")
            )
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    history = list(state.get("history", []))
    history.append(
        SystemMessage(
            content=(
                f"[LIVE MCP TOOL RESULTS — ALREADY FETCHED FOR YOU | Current Time: {now_utc}]\n"
                "The following live web/tool content was just retrieved by VectoCore MCP tools for the user's request.\n"
                "STRICT GROUNDING RULES:\n"
                "1. Prefer the most authoritative, most recent verified source (Result #1). If Result #1 does not contain the needed data, fall back to Result #2, and then Result #3 — never mix contradictory numbers across sites.\n"
                "2. Check dates carefully: if retrieved data is from a previous trading day or the market is closed today, state that explicitly.\n"
                "3. Stick STRICTLY to facts explicitly present in the retrieved tool output below — never fabricate, mix conflicting figures across sources, or fill in details from memory that are absent from the fetched page. If a specific detail requested by the user is not on the fetched page, say so honestly. Cite ONLY the exact verified source URL(s) returned in the tool output below as clickable inline markdown links like [[1]](https://exact-url).\n"
                "4. Do NOT claim you cannot browse the web or fetch external URLs when tool output succeeded — the content is already provided below.\n"
                "5. CRITICAL ANTI-HALLUCINATION RULE: If a tool returned `[... unavailable]` or `[TOOL OUTPUT BLOCKED]` or empty results, DO NOT guess, DO NOT summarize or answer about that URL/query from memory, and DO NOT emit any `[[1]](...)` citation links (never output `[[1]](unavailable)`). Clearly tell the user in 1-2 sentences that the fetch/search failed or was blocked (citing the exact reason given below) and stop.\n\n"
                + "\n".join(results)
            )
        )
    )
    return {"history": history, "skip_cache": True}


def _is_failover_error(exc: Exception) -> tuple[bool, bool]:
    """Return (should_failover, is_daily_quota) for transient rate-limit or availability errors."""
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    is_rate = (
        "ratelimit" in name
        or "toomanyrequests" in name
        or "resourceexhausted" in name
        or "429" in text
        or "rate limit" in text
        or "quota" in text
    )
    is_unavailable = (
        is_rate
        or "503" in text
        or "504" in text
        or "serviceunavailable" in name
        or "deadlineexceeded" in name
        or "timeout" in name
    )
    is_daily = "per-day" in text or "per day" in text or "daily" in text or "rpd" in text
    return is_unavailable, is_daily


def _describe_prompt_activity(message: str, model_label: str, input_lang: str, eff_lang: str) -> str:
    """Build a concise, prompt-aware Claude-style status line from real request context."""
    low = (message or "").lower()
    if any(k in low for k in ("code", "python", "sql", "typescript", "debug", "error", "bug", "function", "example")):
        return f"Analyzing code patterns & examples with {model_label}…"
    if any(k in low for k in ("compare", "difference", "vs ", "architecture", "deep", "step by step", "detail", "research", "tradeoff")):
        return f"Deep-diving & structuring analysis with {model_label}…"
    if input_lang not in ("English", "") or eff_lang not in ("English", ""):
        return f"Translating {input_lang} nuance into {eff_lang} with {model_label}…"
    return f"Thinking & drafting response with {model_label}…"


TIER_RESPONSE_POLICIES: dict[str, str] = {
    "deep_research": (
        "RESPONSE DEPTH POLICY (DEEP RESEARCH TIER — INTENT-GATED):\n"
        "1. DEFAULT MODE (BALANCED): Unless the user intentionally asks for deep, detailed, architectural, comprehensive, or complex research depth, "
        "answer in standard BALANCED mode — provide a clear direct takeaway first with well-organized supporting points or a concise example, "
        "strictly proportional to the user's query and in their requested language (neither overly terse nor exhaustively long). "
        "For straightforward, introductory, or definitional questions (e.g., 'What is Docker?', 'What is system integration?', 'Docker kya hai?', 'डॉकर क्या है?'), "
        "NEVER bloat the response into an exhaustive essay or unrequested deep-research report.\n"
        "2. WHEN TO ACTIVATE FULL DEEP RESEARCH MODE: Switch to a comprehensive, exhaustive, in-depth, deeply structured analysis "
        "(covering overview, full step-by-step reasoning, architecture/internal mechanics, tradeoffs, edge cases, concrete examples or code, and synthesis) "
        "ONLY when the user's query itself intentionally signals a request for depth, detail, or complexity — judged by semantic intent and meaning, "
        "NOT by a single fixed keyword, across ANY phrasing and ANY language (English, Hindi, Hinglish, or other languages).\n"
        "   Equivalent deep/complex intent signals include asking for: a detailed/thorough/exhaustive/in-depth/comprehensive explanation, "
        "a deep dive, a full breakdown, a complete end-to-end guide, architecture/system design/internal workings ('under the hood'), "
        "in-depth comparisons or tradeoffs, root-cause/security/debugging investigation, multi-step research synthesis, "
        "or natural multilingual equivalents with the same intent (e.g., 'detail mein', 'vistaar se', 'gehrai se', 'poori detail/jaankari', "
        "'achhe se step-by-step samjhao', 'andar se kaise kaam karta hai', 'architecture samjhao', "
        "'विस्तार से समझाओ', 'गहराई से विश्लेषण', 'संपूर्ण विवरण', 'आर्किटेक्चर और ट्रेडऑफ़', 'डीप रिसर्च').\n"
        "3. CITATIONS: When tool results are already provided in the conversation context, match the synthesis depth to the active mode above "
        "and ground facts with inline clickable citations [[1]](url). Never attempt to call tools directly."
    ),
    "balanced": (
        "RESPONSE DEPTH POLICY (BALANCED TIER): Provide a balanced, structured answer that combines a clear direct takeaway first "
        "with well-organized supporting details, key points, or a concise example — neither overly terse nor exhaustively long. "
        "When MCP web search or URL-fetch tool results are present, summarize the core answer and key supporting facts with inline clickable citations [[1]](url)."
    ),
    "fast": (
        "RESPONSE DEPTH POLICY (FAST TIER): Provide a crisp, direct, high-signal answer tailored strictly to the user's immediate intent. "
        "Lead with the exact answer in 1-4 sentences or compact bullet points; skip filler, long background, and unnecessary elaboration. "
        "When MCP web search or URL-fetch tool results are present, extract the exact requested facts concisely with inline clickable citations [[1]](url)."
    ),
}


def build_tier_response_policy(tier: str) -> str:
    """Return the system prompt depth policy for the active tier."""
    return TIER_RESPONSE_POLICIES.get(tier, TIER_RESPONSE_POLICIES["balanced"])


async def generate_response(state: ChatState) -> dict[str, Any]:
    """Buffer complete LLM generation with intent-aware dynamic routing and failover."""
    requested_provider = state["provider"]
    requested_model = state["model"]
    history_items = state.get("history", [])
    history_len = len(history_items)
    router = get_quota_router()
    tier, intent_label = resolve_effective_tier(
        requested_provider,
        requested_model,
        message=state["message"],
        history_len=history_len,
    )
    best_provider, best_model, proactive_reason = select_best_model_candidate(
        requested_provider,
        requested_model,
        message=state["message"],
        history_len=history_len,
    )

    raw_candidates = build_fallback_candidates(
        requested_provider,
        requested_model,
        message=state["message"],
        history_len=history_len,
    )
    ordered_candidates = [(best_provider, best_model)] + [
        (opt.provider, opt.id)
        for opt in raw_candidates
        if (opt.provider, opt.id) != (best_provider, best_model)
    ]
    if not ordered_candidates:
        ordered_candidates = [(requested_provider, requested_model)]

    usage_handler = UsageMetadataCallbackHandler()
    eff_lang = state.get("effective_response_language", "English")
    in_lang = state.get("input_language", "English")
    writer = get_stream_writer()

    active_provider = best_provider
    active_model = best_model
    switched_from: str | None = (
        get_model_label(requested_model)
        if (best_provider, best_model) != (requested_provider, requested_model)
        else None
    )
    switch_reason: str | None = proactive_reason

    if switched_from:
        reason_suffix = proactive_reason or f"{intent_label} ({tier} tier)"
        writer({
            "event": "status.update",
            "data": {
                "stage": "model_switch",
                "message": f"Switching to {get_model_label(best_model)} ({reason_suffix})…",
                "switched_from": switched_from,
                "active_model": get_model_label(best_model),
            },
        })

    raw_history = state.get("history", [])
    system_blocks = [str(m.content) for m in raw_history if isinstance(m, SystemMessage) and str(m.content).strip()]
    system_blocks.append(build_tier_response_policy(tier))
    clean_history = [m for m in raw_history if not isinstance(m, SystemMessage)]
    extra_system_context = "\n\n" + "\n\n".join(system_blocks)

    full_text = ""
    last_exc: Exception | None = None
    attempts = 0
    for cand_provider, cand_model in ordered_candidates[:6]:
        attempts += 1
        model_label = get_model_label(cand_model)
        writer({
            "event": "status.update",
            "data": {
                "stage": "generating",
                "message": _describe_prompt_activity(state["message"], model_label, in_lang, eff_lang),
            },
        })
        try:
            router.record_request(cand_provider, cand_model)
            llm = get_chat_model(cand_provider, cand_model, streaming=True)
            chain = state["prompt"] | llm | StrOutputParser()
            chunks: list[str] = []
            async with asyncio.timeout(settings.OPENROUTER_TIMEOUT_SECONDS):
                async for chunk in chain.astream(
                    {
                        "history": clean_history,
                        "message": state["message"],
                        "effective_response_language": eff_lang,
                        "extra_system_context": extra_system_context,
                    },
                    config={"callbacks": [usage_handler]},
                ):
                    if chunk:
                        chunks.append(chunk)
            full_text = "".join(chunks)
            active_provider = cand_provider
            active_model = cand_model
            last_exc = None
            break
        except Exception as exc:
            should_failover, is_daily = _is_failover_error(exc)
            if not should_failover or attempts >= min(6, len(ordered_candidates)):
                raise
            last_exc = exc
            err_low = str(exc).lower()
            is_overload = (
                "503" in err_low
                or "unavailable" in err_low
                or "high demand" in err_low
                or "overload" in err_low
                or "timeout" in type(exc).__name__.lower()
            )
            if is_daily:
                reason_label = "daily quota limit"
            elif is_overload:
                reason_label = "high demand — please use different models"
            else:
                reason_label = "rate limit"
            router.mark_rate_limited(cand_provider, cand_model, is_daily=is_daily, reason=reason_label)
            switched_from = switched_from or get_model_label(requested_model)
            switch_reason = reason_label
            if attempts < len(ordered_candidates):
                next_label = get_model_label(ordered_candidates[attempts][1])
                status_msg = (
                    f"{model_label} is currently experiencing high demand — switching to {next_label}…"
                    if is_overload
                    else f"{model_label} hit {reason_label} — switching to {next_label}…"
                )
                writer({
                    "event": "status.update",
                    "data": {
                        "stage": "model_switch",
                        "message": status_msg,
                    },
                })

    if last_exc is not None:
        raise last_exc

    is_valid = validate_generated_response_language(full_text, eff_lang)

    # Bounded 1-retry if LLM violated effective_response_language
    if not is_valid:
        retry_chunks: list[str] = []
        llm = get_chat_model(active_provider, active_model, streaming=True)
        chain = state["prompt"] | llm | StrOutputParser()
        correction_msg = (
            f"{state['message']}\n\n"
            f"[SYSTEM CORRECTION: Your previous response violated the required response language. "
            f"Write the complete answer strictly in {eff_lang}.]"
        )
        async for chunk in chain.astream(
            {
                "history": clean_history,
                "message": correction_msg,
                "effective_response_language": eff_lang,
                "extra_system_context": extra_system_context,
            },
            config={"callbacks": [usage_handler]},
        ):
            if chunk:
                retry_chunks.append(chunk)
        retry_text = "".join(retry_chunks)
        if retry_text.strip():
            full_text = retry_text
            is_valid = validate_generated_response_language(full_text, eff_lang)

    skip_cache = bool(state.get("skip_cache", False))
    output_blocked = False
    output_reason_category: str | None = None

    # Step 5: Output validation AFTER language-retry loop and BEFORE writer(content.delta) and engine.store()
    out_verdict = await get_guardrails_service().check_output(
        state["message"],
        full_text,
        user_id=state.get("user_id"),
        db=state.get("db"),
    )
    if out_verdict.effective_decision in (Decision.BLOCK, Decision.FALLBACK, Decision.REQUIRE_REVIEW):
        full_text = out_verdict.user_safe_message or "I cannot fulfill this request due to safety guidelines."
        skip_cache = True
        output_blocked = True
        output_reason_category = out_verdict.reason_category or "output_blocked"
    elif out_verdict.effective_decision == Decision.REDACT and out_verdict.redacted_content is not None:
        full_text = out_verdict.redacted_content

    writer({"event": "content.delta", "data": full_text})

    metadata = usage_handler.usage_metadata
    usage: dict[str, Any] = {}
    for value in metadata.values():
        if isinstance(value, dict):
            usage["input_tokens"] = value.get("input_tokens")
            usage["output_tokens"] = value.get("output_tokens")
    return {
        "raw_answer": full_text,
        "usage": usage,
        "language_valid": is_valid,
        "skip_cache": skip_cache,
        "output_blocked": output_blocked,
        "output_reason_category": output_reason_category,
        "active_provider": active_provider,
        "active_model": active_model,
        "switched_from": switched_from,
        "switch_reason": switch_reason,
    }


async def process_response(state: ChatState) -> dict[str, Any]:
    answer = state.get("raw_answer", "").strip()
    if not answer:
        raise RuntimeError("The selected model returned an empty response.")
    return {"answer": answer}


async def persist_response(state: ChatState) -> dict[str, Any]:
    db: AsyncSession = state["db"]
    elapsed_ms = max(0, int((time.perf_counter() - state["started_at"]) * 1000))
    used_provider = state.get("active_provider", state["provider"])
    used_model = state.get("active_model", state["model"])
    is_output_blocked = bool(state.get("output_blocked", False))
    assistant_message = ChatMessage(
        owner_id=state["user_id"],
        conversation_id=state["conversation_id"],
        role="assistant",
        content=state["answer"],
        provider=used_provider,
        model_id=used_model,
        input_tokens=state.get("usage", {}).get("input_tokens"),
        output_tokens=state.get("usage", {}).get("output_tokens"),
        latency_ms=elapsed_ms,
        status="blocked" if is_output_blocked else "completed",
    )
    conversation = await db.scalar(
        select(ChatConversation).where(
            ChatConversation.id == state["conversation_id"],
            ChatConversation.owner_id == state["user_id"],
        )
    )
    if conversation is None:
        raise RuntimeError("Conversation was not found while saving the response.")
    conversation.updated_at = func.now()
    db.add(assistant_message)
    await db.commit()
    await db.refresh(assistant_message)
    assistant_msg_id = assistant_message.id

    # If this was a cache miss, store into cache engine only when response language validation passed.
    if not state.get("is_cached", False):
        if not _supports_postgres_cache(db):
            return {"assistant_message_id": assistant_msg_id, "latency_ms": elapsed_ms}

        try:
            engine = SemanticCacheEngine(db, state["user_id"])
            in_tok = state.get("usage", {}).get("input_tokens") or count_tokens(state["message"])
            out_tok = state.get("usage", {}).get("output_tokens") or count_tokens(state["answer"])
            lookup = state.get("cache_lookup")
            lookup_latency = lookup.lookup_latency_ms if lookup else 0
            eff_lang = state.get("effective_response_language", "English")
            input_lang = state.get("input_language", "English")
            lang_policy = state.get("language_policy", "default")
            allow_global_cache_write = (
                not is_output_blocked
                and state.get("language_valid", True)
                and not state.get("skip_cache", False)
                and not _REFUSAL_RE.search(state.get("answer", "") or "")
            )

            if allow_global_cache_write:
                try:
                    await engine.store(
                        query=state["message"],
                        response=state["answer"],
                        provider=used_provider,
                        model=used_model,
                        input_tokens=in_tok,
                        output_tokens=out_tok,
                        conversation_language_preference=state.get("conversation_language_preference"),
                        effective_response_language=eff_lang,
                        language_policy=lang_policy,
                    )
                except Exception:
                    try:
                        await db.rollback()
                    except Exception:
                        pass

            telemetry_explanation = (
                f"Output blocked by AI Guardrails ({state.get('output_reason_category') or 'policy'})."
                if is_output_blocked
                else (
                    state.get("fetch_reason")
                    if state.get("skip_cache", False)
                    else (lookup.validation_explanation if lookup else None)
                )
            )
            await engine.record_telemetry(
                query=state["message"],
                cache_status="blocked" if is_output_blocked else ("fetch" if state.get("skip_cache", False) else "miss"),
                provider=used_provider,
                model=used_model,
                input_tokens=in_tok,
                output_tokens=out_tok,
                lookup_latency_ms=lookup_latency,
                total_latency_ms=elapsed_ms,
                conversation_id=state["conversation_id"],
                similarity_score=lookup.similarity_score if lookup else None,
                detected_language=input_lang,
                requested_language=eff_lang,
                response_preview=state["answer"],
                current_query=state["message"],
                rejected_candidates_snapshot=lookup.rejected_candidates_snapshot if lookup else None,
                validation_explanation=telemetry_explanation,
            )
        except Exception:
            try:
                await db.rollback()
            except Exception:
                pass

    return {"assistant_message_id": assistant_msg_id, "latency_ms": elapsed_ms}


def build_chat_graph():
    graph = StateGraph(ChatState)
    graph.add_node("validate_request", validate_request)
    graph.add_node("check_cache", check_cache)
    graph.add_node("select_prompt_configuration", select_prompt_configuration)
    graph.add_node("tools_stage", tools_stage)
    graph.add_node("generate_response", generate_response)
    graph.add_node("process_response", process_response)
    graph.add_node("persist_response", persist_response)

    graph.add_edge(START, "validate_request")
    graph.add_edge("validate_request", "check_cache")
    graph.add_conditional_edges(
        "check_cache",
        route_after_cache,
        {
            "process_response": "process_response",
            "select_prompt_configuration": "select_prompt_configuration",
        },
    )
    graph.add_edge("select_prompt_configuration", "tools_stage")
    graph.add_edge("tools_stage", "generate_response")
    graph.add_edge("generate_response", "process_response")
    graph.add_edge("process_response", "persist_response")
    graph.add_edge("persist_response", END)
    return graph.compile()


chat_graph = build_chat_graph()
