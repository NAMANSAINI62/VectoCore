# MCP (Model Context Protocol) Integration Guide

VectoCore uses the official Python `mcp` SDK (`FastMCP` servers + `MCPClientManager`) behind the existing **Tool-Call Firewall** in `backend/app/guardrails/tools.py`.

## Built-in Read-Only MCP Servers
1. **Web Fetch (`fetch__get_page(url)`):** `backend/app/mcp/servers/web_fetch_server.py`
   - Only `http` and `https` schemes.
   - Resolves hostnames and blocks loopback, private (`10/8`, `172.16/12`, `192.168/16`), link-local (`169.254/16` including `169.254.169.254`), multicast, unspecified, and IPv6 equivalents (`::1`, `fc00::/7`, `fe80::/10`, IPv4-mapped).
   - Connects to the checked IP and re-validates on every redirect (max 3).
   - 10s timeout, 1 MB download cap, `text/html` and `text/plain` only.
2. **Web Search (`search__web_search(query)`):** `backend/app/mcp/servers/web_search_server.py`
   - Backed by **Tavily** (`TAVILY_API_KEY` passed only to the server's minimal child env).
   - Returns at most 5 `{title, url, snippet}` results, cached in `_TOOL_TTL_CACHE` (`900s`) to save free-tier credits.

## Adding a New MCP Server Safely
1. Keep the server **read-only** and never expose internal application tables, user records, or telemetry.
2. Add the server entry to your `MCP_SERVERS_CONFIG_PATH` JSON with explicit `allowlisted_tools` and `allowed_env_vars` (never pass `JWT_SECRET_KEY`, `DATABASE_URL`, or LLM keys).
3. Set `MCP_ENABLED=true` in `backend/.env` and restart the backend; verify `MCP server [<name>]: READY` in startup logs.
