"""Configuration schemas and loader for MCP servers, web fetch, and web search."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"


class MCPServerConfig(BaseModel):
    """Configuration for a single MCP server connection."""

    name: str = Field(min_length=1, max_length=64)
    transport: Literal["stdio", "streamable_http"] = "stdio"
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = None
    allowed_env_vars: list[str] = Field(default_factory=list)
    allowlisted_tools: list[str] = Field(default_factory=list)
    timeout_sec: float = Field(default=10.0, gt=0.0, le=60.0)
    read_only: bool = True


class MCPSettings(BaseSettings):
    """MCP client and external web-tool settings."""

    MCP_ENABLED: bool = False
    MCP_SERVERS_CONFIG_PATH: str = ""

    # Web Fetch limits
    WEB_FETCH_TIMEOUT_SEC: float = 10.0
    WEB_FETCH_MAX_BYTES: int = 1_048_576  # 1 MB
    WEB_FETCH_MAX_REDIRECTS: int = 3
    WEB_FETCH_CACHE_TTL_SEC: int = 300
    WEB_FETCH_ALLOWLIST_DOMAINS: str = ""
    WEB_FETCH_BLOCKLIST_DOMAINS: str = ""
    WEB_FETCH_USER_AGENT: str = "VectoCoreBot/1.0 (+https://github.com/NAMANSAINI62/VectoCore)"

    # Web Search (Tavily)
    WEB_SEARCH_PROVIDER: Literal["tavily"] = "tavily"
    WEB_SEARCH_API_KEY_ENV: str = "TAVILY_API_KEY"
    WEB_SEARCH_MAX_RESULTS: int = 5
    WEB_SEARCH_MAX_QUERY_CHARS: int = 200
    WEB_SEARCH_TIMEOUT_SEC: float = 8.0
    WEB_SEARCH_CACHE_TTL_SEC: int = 900

    model_config = SettingsConfigDict(
        env_file=str(_ENV_PATH) if _ENV_PATH.exists() else ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    def load_servers(self) -> list[MCPServerConfig]:
        """Load server definitions from MCP_SERVERS_CONFIG_PATH JSON if configured."""
        path_str = (self.MCP_SERVERS_CONFIG_PATH or "").strip()
        if not path_str:
            return []
        cfg_path = Path(path_str)
        if not cfg_path.is_absolute():
            cfg_path = Path(__file__).resolve().parent.parent.parent / cfg_path
        if not cfg_path.exists():
            return []
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        items = raw.get("servers", raw) if isinstance(raw, dict) else raw
        return [MCPServerConfig.model_validate(item) for item in (items or [])]


def build_minimal_child_env(allowed_env_vars: list[str]) -> dict[str, str]:
    """Construct a minimal subprocess environment containing ONLY explicitly allowlisted variables."""
    safe_sys_keys = ("PATH", "SYSTEMROOT", "COMSPEC", "TEMP", "TMP")
    env: dict[str, str] = {}
    for key in safe_sys_keys:
        val = os.environ.get(key)
        if val is not None:
            env[key] = val
    dotenv_map: dict[str, str | None] = {}
    if _ENV_PATH.exists():
        from dotenv import dotenv_values

        dotenv_map = dotenv_values(_ENV_PATH)

    for key in allowed_env_vars:
        val = os.environ.get(key) or dotenv_map.get(key)
        if val is not None:
            env[key] = val
    return env


@lru_cache
def get_mcp_settings() -> MCPSettings:
    return MCPSettings()
