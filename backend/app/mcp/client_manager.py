"""MCP client lifecycle manager: stdio & streamable HTTP sessions, startup self-tests, and backoff."""

from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

from app.mcp.config import MCPServerConfig, MCPSettings, build_minimal_child_env, get_mcp_settings
from app.mcp.registry import MCPToolRegistry

logger = logging.getLogger("app.mcp.client_manager")


@dataclass
class MCPServerHealth:
    name: str
    transport: str
    status: str = "UNAVAILABLE"  # READY | UNAVAILABLE
    tools: list[str] = field(default_factory=list)
    last_error: str | None = None


class MCPClientManager:
    """Manages MCP server connections in the FastAPI lifespan."""

    def __init__(
        self,
        settings: MCPSettings | None = None,
        registry: MCPToolRegistry | None = None,
    ) -> None:
        self.settings = settings or get_mcp_settings()
        self.registry = registry or MCPToolRegistry()
        self._exit_stack: AsyncExitStack | None = None
        self._sessions: dict[str, Any] = {}
        self._configs: dict[str, MCPServerConfig] = {}
        self._health: dict[str, MCPServerHealth] = {}

    async def startup(self) -> None:
        """Connect to configured MCP servers and run startup self-tests."""
        if not self.settings.MCP_ENABLED:
            logger.info("MCP_ENABLED=false; skipping MCP client startup.")
            return

        self._exit_stack = AsyncExitStack()
        servers = self.settings.load_servers()
        for cfg in servers:
            self._configs[cfg.name] = cfg
            await self._connect_with_backoff(cfg)

    async def _connect_with_backoff(self, cfg: MCPServerConfig, max_attempts: int = 2) -> bool:
        """Connect to one MCP server with exponential backoff; never crash the app."""
        for attempt in range(1, max_attempts + 1):
            try:
                session = await asyncio.wait_for(
                    self._open_session(cfg),
                    timeout=cfg.timeout_sec,
                )
                tools_resp = await asyncio.wait_for(session.list_tools(), timeout=cfg.timeout_sec)
                raw_tools = getattr(tools_resp, "tools", []) or []
                registered = self.registry.register_server_tools(
                    cfg.name,
                    raw_tools,
                    allowlisted_tools=cfg.allowlisted_tools,
                    read_only=cfg.read_only,
                )
                self._sessions[cfg.name] = session
                self._health[cfg.name] = MCPServerHealth(
                    name=cfg.name,
                    transport=cfg.transport,
                    status="READY",
                    tools=[t.namespaced_name for t in registered],
                )
                logger.info("MCP server [%s]: READY (%d allowlisted tools)", cfg.name, len(registered))
                return True
            except Exception as exc:
                err_msg = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "MCP server [%s] attempt %d/%d failed: %s",
                    cfg.name,
                    attempt,
                    max_attempts,
                    err_msg,
                )
                if attempt < max_attempts:
                    await asyncio.sleep(0.5 * attempt)
                else:
                    self._health[cfg.name] = MCPServerHealth(
                        name=cfg.name,
                        transport=cfg.transport,
                        status="UNAVAILABLE",
                        last_error=err_msg,
                    )
                    logger.error("MCP server [%s]: UNAVAILABLE (%s)", cfg.name, err_msg)
        return False

    async def _open_session(self, cfg: MCPServerConfig) -> Any:
        assert self._exit_stack is not None
        from mcp import ClientSession

        if cfg.transport == "stdio":
            from mcp.client.stdio import StdioServerParameters, stdio_client

            if not cfg.command:
                raise ValueError(f"MCP stdio server '{cfg.name}' requires 'command'.")
            params = StdioServerParameters(
                command=cfg.command,
                args=cfg.args,
                env=build_minimal_child_env(cfg.allowed_env_vars),
            )
            read_stream, write_stream = await self._exit_stack.enter_async_context(stdio_client(params))
        else:
            from mcp.client.streamable_http import streamablehttp_client

            if not cfg.url:
                raise ValueError(f"MCP streamable_http server '{cfg.name}' requires 'url'.")
            read_stream, write_stream, _ = await self._exit_stack.enter_async_context(
                streamablehttp_client(cfg.url)
            )

        session = await self._exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
        await session.initialize()
        return session

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> str:
        """Invoke a tool on a connected MCP server, reconnecting once if needed."""
        session = self._sessions.get(server_name)
        cfg = self._configs.get(server_name)
        if session is None and cfg is not None:
            ok = await self._connect_with_backoff(cfg, max_attempts=1)
            if ok:
                session = self._sessions.get(server_name)
        if session is None or cfg is None:
            raise RuntimeError(f"MCP server '{server_name}' is UNAVAILABLE.")

        res = await asyncio.wait_for(
            session.call_tool(tool_name, arguments=arguments),
            timeout=cfg.timeout_sec,
        )
        parts: list[str] = []
        for item in getattr(res, "content", []) or []:
            text = getattr(item, "text", None)
            if text:
                parts.append(text)
        return "\n".join(parts)

    def health_snapshot(self) -> list[dict[str, Any]]:
        """Return read-only server health & allowlisted tool names (zero secrets/commands)."""
        return [
            {
                "name": h.name,
                "transport": h.transport,
                "status": h.status,
                "tools": list(h.tools),
            }
            for h in self._health.values()
        ]

    async def shutdown(self) -> None:
        if self._exit_stack is not None:
            try:
                await self._exit_stack.aclose()
            except Exception as exc:
                logger.warning("Error during MCP shutdown: %s", type(exc).__name__)
            self._exit_stack = None
        self._sessions.clear()


_mcp_manager: MCPClientManager | None = None


def get_mcp_client_manager() -> MCPClientManager:
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = MCPClientManager()
    return _mcp_manager
