"""Redis connection management, exact cache operations, and distributed locking."""

import asyncio
import json
import logging
from typing import Awaitable, Callable, Optional, TypeVar
from urllib.parse import urlparse

import pybreaker
import redis.asyncio as aioredis
from cachetools import TTLCache
from redis.asyncio.lock import Lock as RedisAsyncLock
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_fixed

from app.config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

T = TypeVar("T")

_redis_client: Optional[aioredis.Redis] = None
_last_redis_failure: float = 0.0
_REDIS_FAILURE_COOLDOWN: float = 15.0  # Skip attempting Redis for 15s after an error
_redis_breaker = pybreaker.CircuitBreaker(fail_max=3, reset_timeout=int(_REDIS_FAILURE_COOLDOWN))
_local_memory_cache: TTLCache[str, tuple[str, float]] = TTLCache(maxsize=2048, ttl=259200)
_local_locks: TTLCache[str, float] = TTLCache(maxsize=1024, ttl=60)
_active_redis_locks: dict[str, RedisAsyncLock] = {}


def _is_remote_redis() -> bool:
    host = (urlparse(str(getattr(settings, "REDIS_URL", "") or "")).hostname or "").lower()
    return bool(host and host not in {"127.0.0.1", "localhost", "::1"})


def _op_timeout(base_timeout: float) -> float:
    """Allow wider operation deadlines for WAN/TLS cloud Redis while keeping local checks tight."""
    if _is_remote_redis():
        return max(base_timeout, float(getattr(settings, "REDIS_SOCKET_TIMEOUT", 2.0) or 2.0))
    return base_timeout


def _redis_available(now: float) -> bool:
    if (now - _last_redis_failure) < _REDIS_FAILURE_COOLDOWN:
        return False
    return _redis_breaker.current_state != pybreaker.STATE_OPEN


async def _run_redis_op(op: Callable[[], Awaitable[T]], *, timeout: float = 0.25) -> T:
    """Execute a Redis coroutine with tenacity bounded retry and pybreaker circuit breaking."""
    global _last_redis_failure
    effective_timeout = _op_timeout(timeout)
    now = asyncio.get_running_loop().time()
    if not _redis_available(now):
        raise pybreaker.CircuitBreakerError("Redis circuit breaker open or on cooldown")
    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(2),
            wait=wait_fixed(0.01),
            retry=retry_if_exception_type((OSError, TimeoutError, aioredis.RedisError)),
            reraise=True,
        ):
            with attempt:
                result = await asyncio.wait_for(op(), timeout=effective_timeout)
        _redis_breaker.close()
        return result
    except Exception as exc:
        _last_redis_failure = now
        try:
            _redis_breaker.call(lambda: (_ for _ in ()).throw(exc))
        except Exception:
            pass
        raise


def get_redis_client() -> aioredis.Redis:
    """Get or initialize singleton Redis client with loop awareness."""
    global _redis_client
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _redis_client is not None and current_loop is not None:
        pool = getattr(_redis_client, "connection_pool", None)
        if pool is not None:
            pool_loop = getattr(pool, "_loop", None)
            if pool_loop is not None and (pool_loop.is_closed() or pool_loop is not current_loop):
                _redis_client = None

    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
            socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
        )
    return _redis_client


async def exact_cache_get(key: str) -> Optional[str]:
    """Retrieve exact cache entry from local memory or Redis with TTL-aware sync."""
    global _last_redis_failure
    now = asyncio.get_event_loop().time()

    # 1. Check local fast-path in-memory cache with strict TTL expiration check
    if key in _local_memory_cache:
        val, exp = _local_memory_cache[key]
        if exp is None or exp > now:
            return val
        del _local_memory_cache[key]

    # 2. Check Redis if not on failure cooldown / circuit open
    if not _redis_available(now):
        return None

    try:
        client = get_redis_client()
        val = await _run_redis_op(lambda: client.get(key), timeout=0.25)
        if val is not None:
            ttl_sec = 300
            if hasattr(client, "ttl"):
                try:
                    raw_ttl = await _run_redis_op(lambda: client.ttl(key), timeout=0.20)
                    if isinstance(raw_ttl, int) and raw_ttl > 0:
                        ttl_sec = raw_ttl
                except Exception:
                    pass
            _local_memory_cache[key] = (val, now + float(ttl_sec))
            return val
    except Exception as exc:
        logger.debug(f"Redis get failed ({type(exc).__name__}), entering cooldown: {exc}")

    return None


async def exact_cache_set(key: str, value: str, ex_seconds: Optional[int] = None) -> None:
    """Store exact cache entry in local memory and Redis with matching TTL."""
    now = asyncio.get_event_loop().time()

    # 1. Populate local bounded TTLCache with explicit per-entry expiry
    exp_ts = (now + float(ex_seconds)) if ex_seconds is not None else float("inf")
    _local_memory_cache[key] = (value, exp_ts)

    # 2. Sync to Redis if healthy
    if not _redis_available(now):
        return

    try:
        client = get_redis_client()
        await _run_redis_op(lambda: client.set(key, value, ex=ex_seconds), timeout=0.25)
    except Exception as exc:
        logger.debug(f"Redis set failed ({type(exc).__name__}), entering cooldown: {exc}")


async def exact_cache_clear_owner(owner_id: str) -> int:
    """Delete all exact-cache entries belonging to an owner from local cache and Redis."""
    prefix = f"llm:exact:v1:{owner_id}:"
    removed = 0
    for k in [key for key in list(_local_memory_cache.keys()) if key.startswith(prefix)]:
        _local_memory_cache.pop(k, None)
        removed += 1

    now = asyncio.get_event_loop().time()
    if not _redis_available(now):
        return removed

    try:
        client = get_redis_client()
        cursor = 0
        while True:
            cursor, keys = await _run_redis_op(
                lambda c=cursor: client.scan(cursor=c, match=f"{prefix}*", count=200),
                timeout=0.5,
            )
            if keys:
                await _run_redis_op(lambda ks=keys: client.delete(*ks), timeout=0.5)
                removed += len(keys)
            if not cursor or cursor == 0:
                break
    except Exception as exc:
        logger.debug(f"Redis clear failed ({type(exc).__name__}): {exc}")

    return removed


async def close_redis_connection() -> None:
    """Close active Redis client connection pool."""
    global _redis_client
    if _redis_client is not None:
        try:
            if hasattr(_redis_client, "aclose"):
                await _redis_client.aclose()
            else:
                await _redis_client.close()
        except Exception:
            pass
        try:
            pool = getattr(_redis_client, "connection_pool", None)
            if pool is not None and hasattr(pool, "disconnect"):
                await pool.disconnect()
        except Exception:
            pass
        _redis_client = None


async def acquire_cache_lock(lock_key: str, ttl_seconds: int = 10) -> bool:
    """Acquire a short-lived distributed lock via redis.asyncio.lock.Lock (with bounded TTLCache fallback)."""
    now = asyncio.get_event_loop().time()

    if _redis_available(now):
        try:
            client = get_redis_client()
            lock = client.lock(lock_key, timeout=ttl_seconds, blocking=False)
            acquired = await _run_redis_op(lambda: lock.acquire(blocking=False), timeout=0.25)
            if acquired:
                _active_redis_locks[lock_key] = lock
            return bool(acquired)
        except Exception as exc:
            logger.debug("Redis lock acquire failed (%s); falling back to local lock", type(exc).__name__)

    exp = _local_locks.get(lock_key)
    if exp is not None and exp > now:
        return False
    _local_locks[lock_key] = now + float(ttl_seconds)
    return True


async def release_cache_lock(lock_key: str) -> None:
    """Release a distributed lock safely."""
    _local_locks.pop(lock_key, None)
    lock = _active_redis_locks.pop(lock_key, None)
    try:
        now = asyncio.get_event_loop().time()
        if _redis_available(now):
            if lock is not None:
                await _run_redis_op(lambda: lock.release(), timeout=0.25)
            else:
                client = get_redis_client()
                await _run_redis_op(lambda: client.delete(lock_key), timeout=0.25)
    except Exception:
        pass
