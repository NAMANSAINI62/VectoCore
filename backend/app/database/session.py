"""Database connection management and session factory using SQLAlchemy."""

import asyncio
import logging
import socket
from urllib.parse import urlparse
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from app.config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that yields an asynchronous database session."""
    async with async_session_factory() as session:
        try:
            yield session
        except BaseException:
            await session.rollback()
            raise
        finally:
            await session.close()


def _is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    """Fast check whether the target port is accepting TCP connections."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


async def check_database_health(timeout_seconds: float = 2.0) -> bool:
    """Perform a check against PostgreSQL to verify connectivity."""
    try:
        parsed = urlparse(settings.DATABASE_URL.replace("postgresql+asyncpg://", "http://"))
        host = parsed.hostname or "localhost"
        port = parsed.port or 5432
        port_open = await asyncio.to_thread(_is_port_open, host, port, 0.5)
        if not port_open:
            return False
    except Exception as exc:
        logger.debug(f"Pre-check database port probe failed: {exc}")
        return False

    async def _ping() -> bool:
        from sqlalchemy import text
        async with async_session_factory() as session:
            result = await session.execute(text("SELECT 1"))
            return result.scalar() == 1

    try:
        return await asyncio.wait_for(_ping(), timeout=timeout_seconds)
    except Exception as exc:
        logger.warning(f"PostgreSQL health check failed: {exc}")
        return False
