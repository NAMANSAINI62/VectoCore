"""FastAPI Application entrypoint."""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator
import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.config.settings import get_settings
from app.api.v1.router import api_router
from app.database.base import Base
from app.database.session import engine
from app.cache.redis_client import close_redis_connection

# Import models so SQLAlchemy metadata registers them
import app.models.user
import app.models.auth_otp
import app.models.user_session
import app.models.password_reset
import app.models.chat
import app.models.cache
from app.guardrails.service import get_guardrails_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("semantic_cache_api")
settings = get_settings()


async def _purge_expired_cache_entries_once() -> int:
    """Delete expired cache_entries rows while keeping cache_telemetry, guardrail_events, and chat history intact."""
    from sqlalchemy import delete
    from app.database.session import async_session_factory
    from app.models.cache import CacheEntry

    async with async_session_factory() as session:
        result = await session.execute(
            delete(CacheEntry).where(CacheEntry.expires_at <= datetime.now(timezone.utc))
        )
        await session.commit()
        return int(result.rowcount or 0)


async def _expired_cache_cleanup_loop(interval_seconds: int = 3600) -> None:
    """Periodically purge expired cache_entries rows on startup and every hour."""
    while True:
        try:
            deleted = await _purge_expired_cache_entries_once()
            if deleted > 0:
                logger.info(f"Expired cache cleanup removed {deleted} stale cache_entries row(s).")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"Expired cache cleanup skipped: {exc}")
        await asyncio.sleep(interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup and shutdown routines."""
    logger.info(f"Starting {settings.APP_NAME} in [{settings.APP_ENV}] mode...")

    # Validate guardrails configuration and initialize circuit breakers at startup (fails fast on bad config)
    guardrails_service = get_guardrails_service()
    await guardrails_service.startup(run_self_tests=True)

    from app.mcp.client_manager import get_mcp_client_manager
    mcp_manager = get_mcp_client_manager()
    await mcp_manager.startup()

    # Ensure base ORM tables exist; column evolutions are managed by Alembic migrations
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("PostgreSQL base tables verified successfully.")
    except Exception as exc:
        logger.error(f"Error ensuring database tables: {exc}")

    cleanup_task = asyncio.create_task(_expired_cache_cleanup_loop(interval_seconds=3600))

    yield
    logger.info("Shutting down application resources...")
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    await mcp_manager.shutdown()
    await guardrails_service.shutdown()
    await close_redis_connection()


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Semantic cache platform API with authenticated conversational chat",
    lifespan=lifespan,
    docs_url="/docs" if settings.APP_ENV != "production" else None,
    redoc_url="/redoc" if settings.APP_ENV != "production" else None,
)

# Global exception handler to avoid blank 500 errors and give clear descriptive messages
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled server error on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected server error occurred."},
    )

# CORS Middleware
def _build_allowed_origins() -> list[str]:
    origins: list[str] = []
    candidates = list(settings.CORS_ORIGINS)
    if settings.FRONTEND_URL:
        candidates.append(settings.FRONTEND_URL)
    if settings.APP_ENV != "production":
        candidates.extend([
            "http://localhost:4317",
            "http://127.0.0.1:4317",
            f"http://localhost:{settings.PORT}",
            f"http://127.0.0.1:{settings.PORT}",
        ])
    for origin in candidates:
        normalized = origin.strip().rstrip("/")
        if normalized and normalized not in origins:
            origins.append(normalized)
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_build_allowed_origins(),
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Main API v1 Router inclusion
app.include_router(api_router, prefix="/api/v1")


@app.get("/", tags=["Root"])
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {
        "name": settings.APP_NAME,
        "version": "1.0.0",
        "health_check": "/api/v1/health",
        "docs": "/docs",
    }


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=settings.PORT, reload=True)
