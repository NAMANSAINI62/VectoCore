# MCP (Model Context Protocol) Integration Guide

VectoCore uses the official Python `mcp` SDK (`MCPServer` stdio servers + `MCPClientManager`) behind the deny-by-default **Tool-Call Firewall** in `backend/app/guardrails/tools.py`.

## Built-in Read-Only MCP Servers (Strictly Separated)
1. **Web Fetch (`fetch__get_page(url)`):** `backend/app/mcp/servers/web_fetch_server.py`
   - Triggered ONLY when the user prompt includes an `http://` or `https://` URL (never falls back to web search).
   - Resolves hostnames and blocks loopback, private (`10/8`, `172.16/12`, `192.168/16`), link-local (`169.254/16` including `169.254.169.254`), multicast, unspecified, and IPv6 equivalents (`::1`, `fc00::/7`, `fe80::/10`, IPv4-mapped).
   - Connects to the validated IP with SNI pinning and re-validates on every redirect (max 5).
   - 10s timeout, clean 2 MB stream cap, strips `<script>/<style>/<svg>/<nav>/<header>/<footer>/<aside>` preferring `<main>/<article>` + meta description, UTF-8 JSON (`ensure_ascii=False`), up to 3,500 extracted chars (`MAX_TOOL_OUTPUT_CHARS=4000`), cached for `300s` in `_TOOL_TTL_CACHE` (errors raise `ToolError` and are never cached).
2. **Web Search (`search__web_search(query)`):** `backend/app/mcp/servers/web_search_server.py`
   - Triggered ONLY on live web-search/real-time/multilingual search prompts without a URL.
   - Backed by **Tavily** (`TAVILY_API_KEY` passed only via minimal child env).
   - Returns at most 3 `{title, url, snippet}` results (550-char snippets, UTF-8 JSON), cached in `_TOOL_TTL_CACHE` (`900s`) to save free-tier credits.

## Adding a New MCP Server Safely
1. Keep the server **read-only** and never expose internal application tables, user records, or telemetry.
2. Add the server entry to `backend/mcp_servers.json` (`MCP_SERVERS_CONFIG_PATH`) with explicit `allowlisted_tools` and `allowed_env_vars` (never pass `JWT_SECRET_KEY`, `DATABASE_URL`, or LLM keys).
3. Set `MCP_ENABLED=true` in `backend/.env` and restart the backend; verify `MCP server [<name>]: READY` in startup logs.
