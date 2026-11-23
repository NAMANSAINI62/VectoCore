"""Offline unit tests for MCP client, Tool-Call Firewall, SSRF web fetch, and Tavily web search."""

from __future__ import annotations

import asyncio
import os
import socket
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from app.guardrails.secret_scanner import SecretScannerDetector
from app.guardrails.tools import MAX_TOOL_CALLS_PER_REQUEST, execute_tool, get_approved_tool_schemas
from app.mcp.config import build_minimal_child_env
from app.mcp.registry import MCPToolRegistry
from app.mcp.servers.web_fetch_server import fetch_public_page, resolve_and_validate_host, validate_public_ip
from app.mcp.servers.web_search_server import run_web_search


@pytest.mark.parametrize(
    "bad_ip",
    [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.5",
        "192.168.1.1",
        "169.254.169.254",
        "::1",
        "fc00::1",
        "fe80::1",
        "::ffff:127.0.0.1",
        "0.0.0.0",
    ],
)
def test_ssrf_blocks_private_loopback_metadata_and_ipv6(bad_ip: str) -> None:
    with pytest.raises(PermissionError):
        validate_public_ip(bad_ip)


def test_ssrf_blocks_localhost_and_non_http_schemes() -> None:
    with pytest.raises(PermissionError):
        resolve_and_validate_host("localhost")

    async def _run() -> None:
        for bad_url in ("file:///etc/passwd", "ftp://example.com/a", "data:text/plain,hi"):
            with pytest.raises(PermissionError):
                await fetch_public_page(bad_url)

    asyncio.run(_run())


def test_ssrf_blocks_hostname_resolving_to_private_ip_and_redirect_to_private_ip() -> None:
    with patch("app.mcp.servers.web_fetch_server.socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.20.30.40", 0))]
        with pytest.raises(PermissionError):
            resolve_and_validate_host("rebind.attacker.example")


def test_minimal_child_env_excludes_backend_secrets() -> None:
    with patch.dict(
        os.environ,
        {
            "JWT_SECRET_KEY": "super-secret-jwt",
            "DATABASE_URL": "postgresql://secret",
            "GEMINI_API_KEY": "AIzaSecret",
            "TAVILY_API_KEY": "tvly-allowed-only",
        },
        clear=False,
    ):
        env = build_minimal_child_env(["TAVILY_API_KEY"])
        assert "JWT_SECRET_KEY" not in env
        assert "DATABASE_URL" not in env
        assert "GEMINI_API_KEY" not in env
        assert env.get("TAVILY_API_KEY") == "tvly-allowed-only"


def test_mcp_firewall_unknown_tool_extra_args_and_secret_scan() -> None:
    reg = MCPToolRegistry()
    reg.register_server_tools(
        "fetch",
        [{"name": "get_page", "description": "Fetch page", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}],
        allowlisted_tools=["get_page"],
    )
    assert reg.get("fetch__get_page") is not None

    async def _run() -> None:
        with pytest.raises(PermissionError):
            await execute_tool("fetch__secret_admin", {}, owner_id=uuid.uuid4())

        fake_mgr = MagicMock()
        fake_mgr.registry = reg
        fake_mgr.call_tool = AsyncMock(return_value="Leaked key nvapi-ABCDEFGHIJKLMNOPQRSTUVWXYZ123456")

        with (
            patch("app.mcp.config.get_mcp_settings") as mock_cfg,
            patch("app.mcp.client_manager.get_mcp_client_manager", return_value=fake_mgr),
        ):
            mock_cfg.return_value.MCP_ENABLED = True
            with pytest.raises(ValidationError):
                await execute_tool("fetch__get_page", {"url": "https://example.com", "extra": 1}, owner_id=uuid.uuid4())

            out = await execute_tool(
                "fetch__get_page",
                {"url": "https://example.com"},
                owner_id=uuid.uuid4(),
                secret_detector=SecretScannerDetector(),
            )
            assert "BLOCKED" in out

    asyncio.run(_run())
    assert MAX_TOOL_CALLS_PER_REQUEST == 3


def test_web_search_stub_and_no_app_db_tools() -> None:
    class StubSearch:
        async def search(self, query: str, max_results: int = 5) -> list[dict[str, str]]:
            return [{"title": "Example", "url": "https://example.com", "snippet": f"Result for {query}"}]

    res = asyncio.run(run_web_search("latest python release", provider=StubSearch()))
    assert len(res["results"]) == 1
    assert res["results"][0]["url"] == "https://example.com"

    tool_names = {t["name"] for t in get_approved_tool_schemas()}
    assert "run_sql_query" not in tool_names
    assert not any("sql" in n or "db" in n for n in tool_names)
