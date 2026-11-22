"""Unit tests for Job 5: Deny-by-default tool calling, strict schemas, owner_id isolation, call cap, and no caching."""

import asyncio
import uuid

import pytest
from pydantic import ValidationError

from app.guardrails.tools import (
    MAX_TOOL_CALLS_PER_REQUEST,
    execute_tool,
    safe_eval_ast,
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
            await execute_tool("calculator", {"expression": "2+2", "extra": 1}, owner_id=uuid.uuid4())
        with pytest.raises(ValidationError):
            await execute_tool(
                "search_my_conversations",
                {"query": "redis", "user_id": "attacker-id"},
                owner_id=uuid.uuid4(),
            )

    asyncio.run(_run())


def test_calculator_safe_ast_blocks_eval_and_call_cap_constant() -> None:
    assert safe_eval_ast("2 + 3 * 4") == 14.0
    with pytest.raises(ValueError):
        safe_eval_ast("__import__('os').system('echo pwned')")
    assert MAX_TOOL_CALLS_PER_REQUEST == 3
    assert supports_tool_calling("openai/gpt-oss-20b") is True
    assert supports_tool_calling("unknown-model") is False
