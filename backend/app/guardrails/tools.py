"""Minimal, deny-by-default tool-calling subsystem with strict Pydantic schemas and untrusted-output scanning."""

import ast
import operator
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatConversation

MAX_TOOL_CALLS_PER_REQUEST = 3
MAX_TOOL_OUTPUT_CHARS = 2000

_ALLOWED_AST_OPS: dict[type[ast.AST], Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

ALLOWED_TIMEZONES = frozenset({
    "UTC",
    "Asia/Kolkata",
    "America/New_York",
    "America/Los_Angeles",
    "Europe/London",
    "Asia/Tokyo",
})

ALLOWED_WEATHER_HOST = "api.open-meteo.com"

# Capability flag per configured model
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


class CalculatorArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expression: str = Field(min_length=1, max_length=120)


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


class WeatherArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)


class SearchConversationsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=120)
    limit: int = Field(default=5, ge=1, le=10)


ALLOWED_TOOLS: dict[str, type[BaseModel]] = {
    "calculator": CalculatorArgs,
    "get_current_time": CurrentTimeArgs,
    "get_weather": WeatherArgs,
    "search_my_conversations": SearchConversationsArgs,
}


def safe_eval_ast(expr: str) -> float:
    """Evaluate basic arithmetic AST safely without eval()."""
    tree = ast.parse(expr, mode="eval")

    def _eval(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_AST_OPS:
            return float(_ALLOWED_AST_OPS[type(node.op)](_eval(node.left), _eval(node.right)))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_AST_OPS:
            return float(_ALLOWED_AST_OPS[type(node.op)](_eval(node.operand)))
        raise ValueError(f"Disallowed AST node: {type(node).__name__}")

    return _eval(tree)


async def execute_tool(
    name: str,
    raw_args: dict[str, Any],
    *,
    owner_id: Any,
    db: AsyncSession | None = None,
    injection_detector: Any | None = None,
) -> str:
    """Execute an allowlisted tool with strict schema validation and untrusted-output scanning."""
    if name not in ALLOWED_TOOLS:
        raise PermissionError(f"Tool '{name}' is denied by default policy.")

    schema_cls = ALLOWED_TOOLS[name]
    parsed = schema_cls.model_validate(raw_args)

    if name == "calculator":
        assert isinstance(parsed, CalculatorArgs)
        output = str(safe_eval_ast(parsed.expression))
    elif name == "get_current_time":
        assert isinstance(parsed, CurrentTimeArgs)
        if parsed.timezone not in ALLOWED_TIMEZONES:
            raise PermissionError("Timezone not allowlisted.")
        output = datetime.now(ZoneInfo(parsed.timezone)).isoformat()
    elif name == "get_weather":
        assert isinstance(parsed, WeatherArgs)
        url = f"https://{ALLOWED_WEATHER_HOST}/v1/forecast"
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                url,
                params={"latitude": parsed.latitude, "longitude": parsed.longitude, "current_weather": "true"},
            )
            r.raise_for_status()
            output = r.text[:4096]
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
    else:
        raise PermissionError(f"Tool '{name}' is denied.")

    truncated = output[:MAX_TOOL_OUTPUT_CHARS]
    if injection_detector is not None and getattr(injection_detector, "available", False):
        res = await injection_detector.check(truncated, layer="tool")
        if res.decision.value in ("BLOCK", "FALLBACK"):
            return "[TOOL OUTPUT BLOCKED: potential prompt injection detected]"
    return truncated
