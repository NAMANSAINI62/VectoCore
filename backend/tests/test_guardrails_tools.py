"""Unit tests for deny-by-default MCP tool firewall, strict schemas, owner_id isolation, and wrapped TTL cache."""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from app.guardrails.tools import (
    MAX_TOOL_CALLS_PER_REQUEST,
    _TOOL_TTL_CACHE,
    execute_tool,
)
from app.mcp.registry import MCPToolRegistry


def test_unknown_and_removed_builtin_tools_denied_by_default() -> None:
    async def _run() -> None:
        for denied_tool in (
            "delete_database",
            "run_sql_query",
            "get_current_time",
            "search_my_conversations",
            "fetch_url",
        ):
            with pytest.raises(PermissionError):
                await execute_tool(denied_tool, {}, owner_id=uuid.uuid4())

    asyncio.run(_run())
    assert MAX_TOOL_CALLS_PER_REQUEST == 3


def test_mcp_extra_args_and_model_supplied_user_id_rejected() -> None:
    reg = MCPToolRegistry()
    reg.register_server_tools(
        "search",
        [
            {
                "name": "web_search",
                "description": "Search web",
                "inputSchema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}, "user_id": {"type": "string"}},
                    "required": ["query"],
                },
            }
        ],
        allowlisted_tools=["web_search"],
    )
    fake_mgr = MagicMock()
    fake_mgr.registry = reg

    async def _run() -> None:
        with (
            patch("app.mcp.config.get_mcp_settings") as mock_cfg,
            patch("app.mcp.client_manager.get_mcp_client_manager", return_value=fake_mgr),
        ):
            mock_cfg.return_value.MCP_ENABLED = True
            with pytest.raises(ValidationError):
                await execute_tool("search__web_search", {"query": "redis", "extra": 1}, owner_id=uuid.uuid4())
            with pytest.raises(ValidationError):
                await execute_tool(
                    "search__web_search",
                    {"query": "redis", "user_id": "attacker-id"},
                    owner_id=uuid.uuid4(),
                )

    asyncio.run(_run())


def test_cached_tool_output_remains_wrapped_in_untrusted_tags() -> None:
    _TOOL_TTL_CACHE.clear()
    reg = MCPToolRegistry()
    reg.register_server_tools(
        "fetch",
        [
            {
                "name": "get_page",
                "description": "Fetch page",
                "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
            }
        ],
        allowlisted_tools=["get_page"],
    )
    fake_mgr = MagicMock()
    fake_mgr.registry = reg
    fake_mgr.call_tool = AsyncMock(return_value='{"title":"Example","content":"Safe text"}')

    async def _run() -> None:
        with (
            patch("app.mcp.config.get_mcp_settings") as mock_cfg,
            patch("app.mcp.client_manager.get_mcp_client_manager", return_value=fake_mgr),
        ):
            mock_cfg.return_value.MCP_ENABLED = True
            first = await execute_tool("fetch__get_page", {"url": "https://example.com"}, owner_id=uuid.uuid4())
            second = await execute_tool("fetch__get_page", {"url": "https://example.com"}, owner_id=uuid.uuid4())
            assert "<untrusted_tool_output" in first
            assert "<untrusted_tool_output" in second
            assert first == second
            assert fake_mgr.call_tool.await_count == 1

    try:
        asyncio.run(_run())
    finally:
        _TOOL_TTL_CACHE.clear()
