"""Read-only Web Search MCP server (`search__web_search`) backed by Tavily."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Protocol

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

mcp = MCPServer("search")

_MAX_RESULTS = 3
_MAX_QUERY_CHARS = 200
_TIMEOUT_SEC = 10.0
_NEWS_QUERY_RE = re.compile(
    r"(?:\b(?:news|breaking|headline|headlines|samachar|khabar|taaza|taza|nifty|sensex|ipl|match|score|noticias|actualit[ée]s|nachrichten)\b|"
    r"समाचार|खबर|खबरें|ताज़ा|ताजा|मैच|स्कोर)",
    re.IGNORECASE,
)


class SearchProvider(Protocol):
    async def search(self, query: str, max_results: int = _MAX_RESULTS) -> list[dict[str, str]]: ...


class TavilySearchProvider:
    """Tavily Search API client reading TAVILY_API_KEY from its own process environment."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = (api_key if api_key is not None else os.environ.get("TAVILY_API_KEY", "")).strip()

    async def search(self, query: str, max_results: int = _MAX_RESULTS) -> list[dict[str, str]]:
        if not self._api_key:
            raise RuntimeError("Search provider UNAVAILABLE: missing TAVILY_API_KEY.")
        is_news = bool(_NEWS_QUERY_RE.search(query))
        base_payload: dict[str, Any] = {
            "api_key": self._api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "advanced",
        }
        payload = {**base_payload, "topic": "news", "days": 3} if is_news else base_payload
        async with httpx.AsyncClient(timeout=_TIMEOUT_SEC) as client:
            resp = await client.post("https://api.tavily.com/search", json=payload)
            resp.raise_for_status()
            data = resp.json()
            raw_items = data.get("results") or []
            if is_news and not raw_items:
                resp = await client.post("https://api.tavily.com/search", json=base_payload)
                resp.raise_for_status()
                data = resp.json()
                raw_items = data.get("results") or []
        results: list[dict[str, str]] = []
        for item in raw_items[:max_results]:
            entry: dict[str, str] = {
                "title": str(item.get("title", ""))[:140],
                "url": str(item.get("url", "")),
                "snippet": str(item.get("content", ""))[:550],
            }
            if item.get("published_date"):
                entry["published_date"] = str(item["published_date"])
            results.append(entry)
        return results


async def run_web_search(query: str, provider: SearchProvider | None = None) -> dict[str, Any]:
    cleaned = (query or "").strip()
    if not cleaned or len(cleaned) > _MAX_QUERY_CHARS:
        raise ValueError(f"Query must be 1..{_MAX_QUERY_CHARS} characters.")
    prov = provider or TavilySearchProvider()
    results = await prov.search(cleaned, max_results=_MAX_RESULTS)
    return {"query": cleaned, "results": results[:_MAX_RESULTS]}


@mcp.tool()
async def web_search(query: str) -> str:
    """Search the public web for current information (read-only, max 3 results)."""
    try:
        data = await run_web_search(query)
        return json.dumps(data, ensure_ascii=False)
    except (ValueError, RuntimeError, httpx.HTTPError) as exc:
        raise ToolError(str(exc)) from exc


if __name__ == "__main__":
    mcp.run()
