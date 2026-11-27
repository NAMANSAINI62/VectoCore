"""Application configuration module using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"



class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    APP_NAME: str = "Semantic Caching SaaS"
    APP_ENV: Literal["development", "staging", "production", "test"] = "development"
    DEBUG: bool = False
    PORT: int = 9417
    SECRET_KEY: str = "default_insecure_development_key_change_in_prod"

    # PostgreSQL Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/semantic_cache_db"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    # Redis Cache
    REDIS_URL: str = "redis://127.0.0.1:6379/0"
    REDIS_SOCKET_TIMEOUT: float = 2.0
    REDIS_CONNECT_TIMEOUT: float = 2.0
    REDIS_MAX_CONNECTIONS: int = 20

    # OpenRouter AI configuration
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    CHAT_AVAILABLE_MODELS: str = "baidu/ernie-5.5-flash-preview:free"
    OPENROUTER_TIMEOUT_SECONDS: float = 180.0

    # Chat provider configuration. Secrets are sourced from the backend environment.
    GROQ_API_KEY: str = ""
    GROQ_DEFAULT_MODEL: str = "openai/gpt-oss-20b"
    GROQ_AVAILABLE_MODELS: str = "openai/gpt-oss-20b,openai/gpt-oss-120b"

    GEMINI_API_KEY: str = ""
    GEMINI_AVAILABLE_MODELS: str = (
        "gemini-3-flash-preview,"
        "gemini-3.5-flash-lite,"
        "gemini-3.1-flash-lite,gemini-3.1-flash-lite-preview,gemini-flash-lite-latest"
    )

    COHERE_API_KEY: str = ""
    COHERE_AVAILABLE_MODELS: str = "command-a-03-2025"

    NVIDIA_API_KEY: str = ""
    NVIDIA_AVAILABLE_MODELS: str = "nvidia/nemotron-3.5-super-vl-120b-a12b,nvidia/nemotron-3.5-bolt-e4b"

    NVIDIA_EMBED_API_KEY: str = ""
    EMBEDDING_MODEL_NAME: str = "nvidia/nemotron-3.5-embed-1b"

    CHAT_DEFAULT_PROVIDER: str = "groq"
    GROQ_STT_MODEL: str = "whisper-large-v3-turbo"

    # JWT Authentication & Security
    JWT_SECRET_KEY: str = "super_secure_jwt_secret_key_change_in_production_min_32_characters"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    COOKIE_SECURE: bool = False  # Set to True in production (HTTPS)
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"

    # Frontend URL
    FRONTEND_URL: str = "http://localhost:4317"

    # Google OAuth 2.0
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:4317/api/v1/auth/google/callback"

    # Brevo / SMTP & Passwordless Email OTP
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_USE_TLS: bool = True
    BREVO_API_KEY: str = ""
    EMAIL_OTP_EXPIRE_MINUTES: int = 5
    EMAIL_OTP_MAX_ATTEMPTS: int = 5

    # CORS
    CORS_ORIGINS: Annotated[list[str], NoDecode] = [
        "http://localhost:4317",
        "http://127.0.0.1:4317",
    ]

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: Any) -> Any:
        """Normalize managed Postgres URLs (postgres://, sslmode=require) for asyncpg."""
        if not isinstance(value, str):
            return value
        raw = value.strip()
        if raw.startswith("postgres://"):
            raw = "postgresql+asyncpg://" + raw[len("postgres://"):]
        elif raw.startswith("postgresql://"):
            raw = "postgresql+asyncpg://" + raw[len("postgresql://"):]

        parsed = urlparse(raw)
        if parsed.query:
            params = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)]
            updated: list[tuple[str, str]] = []
            for k, v in params:
                if k == "sslmode":
                    if not any(pk == "ssl" for pk, _ in params):
                        updated.append(("ssl", "require" if v in ("require", "verify-ca", "verify-full") else v))
                elif k != "channel_binding":
                    updated.append((k, v))
            raw = urlunparse(parsed._replace(query=urlencode(updated)))
        return raw

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: Any) -> Any:
        """Accept either a JSON list or comma-separated origins from cloud env vars."""
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                import json

                parsed = json.loads(stripped)
                return [str(item).strip().rstrip("/") for item in parsed if str(item).strip()]
            return [item.strip().rstrip("/") for item in stripped.split(",") if item.strip()]
        if isinstance(value, list):
            return [str(item).strip().rstrip("/") for item in value if str(item).strip()]
        return value

    model_config = SettingsConfigDict(
        env_file=str(_ENV_PATH) if _ENV_PATH.exists() else ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()

