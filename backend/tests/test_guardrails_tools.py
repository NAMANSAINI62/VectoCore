"""Unit tests for deny-by-default tool calling, strict schemas, owner_id isolation, call cap, and firewall checks."""

import asyncio
import uuid

import pytest
from pydantic import ValidationError

from app.guardrails.tools import (
    MAX_TOOL_CALLS_PER_REQUEST,
    execute_tool,
    supports_tool_calling,
)


def test_unknown_tool_denied_by_default() -> None:
    async def _run() -> None:
        with pytest.raises(PermissionError):
            await execute_tool("delete_database", {}, owner_id=uuid.uuid4())

    asyncio.run(_run())


def test_extra_args_and_model_supplied_user_id_rejected() -> None:
    async def _run() -> None:
        with pytest.raises(ValidationError):
            await execute_tool("get_current_time", {"timezone": "UTC", "extra": 1}, owner_id=uuid.uuid4())
        with pytest.raises(ValidationError):
            await execute_tool(
                "search_my_conversations",
                {"query": "redis", "user_id": "attacker-id"},
                owner_id=uuid.uuid4(),
            )

    asyncio.run(_run())


def test_tool_firewall_blocks_unsafe_sql_and_ssrf_and_checks_caps() -> None:
    async def _run() -> None:
        with pytest.raises(PermissionError):
            await execute_tool("run_sql_query", {"query": "DROP TABLE users"}, owner_id=uuid.uuid4())
        with pytest.raises(PermissionError):
            await execute_tool("fetch_url", {"url": "http://127.0.0.1:8080/admin"}, owner_id=uuid.uuid4())

    asyncio.run(_run())
    assert MAX_TOOL_CALLS_PER_REQUEST == 3
    assert supports_tool_calling("openai/gpt-oss-20b") is True
    assert supports_tool_calling("unknown-model") is False
