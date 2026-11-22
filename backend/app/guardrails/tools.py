"""Minimal, deny-by-default tool-calling subsystem with strict Pydantic schemas, TTL cache, and Tool-Call Firewall."""

import json
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatConversation

MAX_TOOL_CALLS_PER_REQUEST = 3
MAX_TOOL_OUTPUT_CHARS = 2000

TOOL_TTL_SECONDS: dict[str, int] = {
    "fetch_url": 3600,            # 1h (web docs)
    "get_current_time": 0,        # 0s (always live)
    "search_my_conversations": 60,
    "run_sql_query": 60,
}
_TOOL_TTL_CACHE: dict[str, tuple[float, str]] = {}

ALLOWED_TIMEZONES = frozenset({
    "UTC",
    "Asia/Kolkata",
    "America/New_York",
    "America/Los_Angeles",
    "Europe/London",
    "Asia/Tokyo",
})

MODEL_TOOL_CAPABILITY: dict[str, bool] = {
    "openai/gpt-oss-20b": True,
    "openai/gpt-oss-120b": True,
    "gemma-4-31b-it": True,
    "gemini-3.8-flash": True,
    "gemini-3-flash-preview": True,
    "gemini-3.5-flash-lite": True,
    "gemini-3.1-flash-lite": True,
    "gemini-3.1-flash-lite-preview": True,
    "gemini-flash-lite-latest": True,
}


def supports_tool_calling(model_id: str) -> bool:
    return MODEL_TOOL_CAPABILITY.get(model_id, False)


class CurrentTimeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timezone: Literal[
        "UTC",
        "Asia/Kolkata",
        "America/New_York",
        "America/Los_Angeles",
        "Europe/London",
        "Asia/Tokyo",
    ] = "UTC"


class SearchConversationsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=120)
    limit: int = Field(default=5, ge=1, le=10)


_FORBIDDEN_SQL_RE = re.compile(
    r"\b(DROP|DELETE|TRUNCATE|ALTER|UPDATE|INSERT|GRANT|REVOKE|EXEC|EXECUTE|MERGE|CREATE|REPLACE)\b|;--",
    re.IGNORECASE,
)


class RunSqlQueryArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=500)


class FetchUrlArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=4, max_length=300)


ALLOWED_TOOLS: dict[str, type[BaseModel]] = {
    "get_current_time": CurrentTimeArgs,
    "search_my_conversations": SearchConversationsArgs,
    "run_sql_query": RunSqlQueryArgs,
    "fetch_url": FetchUrlArgs,
}


async def execute_tool(
    name: str,
    raw_args: dict[str, Any],
    *,
    owner_id: Any,
    db: AsyncSession | None = None,
    injection_detector: Any | None = None,
) -> str:
    """Execute an allowlisted tool with strict schema validation, TTL cache, and firewall checks."""
    if name not in ALLOWED_TOOLS:
        raise PermissionError(f"Tool '{name}' is denied by default policy.")

    schema_cls = ALLOWED_TOOLS[name]
    parsed = schema_cls.model_validate(raw_args)

    ttl = TOOL_TTL_SECONDS.get(name, 0)
    cache_key = f"{name}:{json.dumps(parsed.model_dump(), sort_keys=True)}"
    if ttl > 0:
        cached = _TOOL_TTL_CACHE.get(cache_key)
        if cached and cached[0] > time.monotonic():
            return cached[1]

    if name == "get_current_time":
        assert isinstance(parsed, CurrentTimeArgs)
        if parsed.timezone not in ALLOWED_TIMEZONES:
            raise PermissionError("Timezone not allowlisted.")
        try:
            tz: Any = ZoneInfo(parsed.timezone)
        except ZoneInfoNotFoundError:
            _offsets = {
                "UTC": timedelta(0),
                "Asia/Kolkata": timedelta(hours=5, minutes=30),
                "America/New_York": timedelta(hours=-5),
                "America/Los_Angeles": timedelta(hours=-8),
                "Europe/London": timedelta(0),
                "Asia/Tokyo": timedelta(hours=9),
            }
            tz = timezone(_offsets[parsed.timezone])
        output = datetime.now(tz).isoformat()
    elif name == "search_my_conversations":
        assert isinstance(parsed, SearchConversationsArgs)
        if db is None:
            output = "[]"
        else:
            rows = (
                await db.scalars(
                    select(ChatConversation.title)
                    .where(
                        ChatConversation.owner_id == owner_id,
                        ChatConversation.title.ilike(f"%{parsed.query}%"),
                    )
                    .limit(parsed.limit)
                )
            ).all()
            output = str(list(rows))
    elif name == "run_sql_query":
        assert isinstance(parsed, RunSqlQueryArgs)
        q = parsed.query.strip()
        if _FORBIDDEN_SQL_RE.search(q) or not q.lower().startswith("select "):
            raise PermissionError("Tool Firewall BLOCKED: only read-only SELECT queries are permitted.")
        output = f"[SIMULATED SAFE SQL RESULT] Executed read-only query: {q}"
    elif name == "fetch_url":
        assert isinstance(parsed, FetchUrlArgs)
        u = urlparse(parsed.url.strip())
        host = (u.hostname or "").lower()
        if u.scheme not in ("http", "https") or host in ("localhost", "127.0.0.1", "0.0.0.0") or host.startswith(("10.", "192.168.", "169.254.")):
            raise PermissionError(f"Tool Firewall BLOCKED: SSRF/internal host '{host or u.scheme}' is not allowed.")
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            r = await client.get(parsed.url.strip(), headers={"User-Agent": "VectorCacheBot/1.0"})
            r.raise_for_status()
            raw_html = r.text
        title_match = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
        title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else host
        clean = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw_html, flags=re.IGNORECASE | re.DOTALL)
        clean = re.sub(r"<[^>]+>", " ", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        output = json.dumps({
            "source_url": str(r.url),
            "title": title[:120],
            "content": clean[:1400],
            "citation_instruction": "Cite this source_url in your answer.",
        })
    else:
        raise PermissionError(f"Tool '{name}' is denied.")

    truncated = output[:MAX_TOOL_OUTPUT_CHARS]
    if injection_detector is not None and getattr(injection_detector, "available", False):
        res = await injection_detector.check(truncated, layer="tool")
        if res.decision.value in ("BLOCK", "FALLBACK"):
            return "[TOOL OUTPUT BLOCKED: potential prompt injection detected]"
    if ttl > 0:
        _TOOL_TTL_CACHE[cache_key] = (time.monotonic() + ttl, truncated)
    return truncated
