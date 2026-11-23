"""Registry of discovered, allowlisted MCP tools namespaced as `<server>__<tool>`."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DiscoveredMCPTool:
    """Metadata and JSON schema for a single allowlisted MCP tool."""

    namespaced_name: str
    server_name: str
    tool_name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    read_only: bool = True


class MCPToolRegistry:
    """In-memory registry of allowlisted MCP tools."""

    def __init__(self) -> None:
        self._tools: dict[str, DiscoveredMCPTool] = {}

    def register_server_tools(
        self,
        server_name: str,
        raw_tools: list[Any],
        *,
        allowlisted_tools: list[str],
        read_only: bool = True,
    ) -> list[DiscoveredMCPTool]:
        """Register only tools explicitly present in `allowlisted_tools`."""
        self.clear_server(server_name)
        allowed = set(allowlisted_tools)
        registered: list[DiscoveredMCPTool] = []
        for tool in raw_tools:
            t_name = getattr(tool, "name", None) or (tool.get("name") if isinstance(tool, dict) else None)
            if not t_name or t_name not in allowed:
                continue
            desc = getattr(tool, "description", None) or (tool.get("description", "") if isinstance(tool, dict) else "")
            schema = (
                getattr(tool, "input_schema", None)
                or getattr(tool, "inputSchema", None)
                or (tool.get("input_schema") or tool.get("inputSchema", {}) if isinstance(tool, dict) else {})
            )
            ns = f"{server_name}__{t_name}"
            entry = DiscoveredMCPTool(
                namespaced_name=ns,
                server_name=server_name,
                tool_name=t_name,
                description=desc or "",
                input_schema=dict(schema or {}),
                read_only=read_only,
            )
            self._tools[ns] = entry
            registered.append(entry)
        return registered

    def clear_server(self, server_name: str) -> None:
        to_del = [k for k, v in self._tools.items() if v.server_name == server_name]
        for k in to_del:
            del self._tools[k]

    def get(self, namespaced_name: str) -> DiscoveredMCPTool | None:
        return self._tools.get(namespaced_name)

    def list_tools(self) -> list[DiscoveredMCPTool]:
        return list(self._tools.values())
