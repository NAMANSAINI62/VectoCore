"""Redis-backed sliding-window rate limiting, concurrency caps, and abuse throttling."""

import inspect
import logging
import time
import uuid
from typing import Any

from fastapi import HTTPException

from app.cache.redis_client import get_redis_client
from app.guardrails.config.settings import GuardrailsSettings, get_guardrails_settings

logger = logging.getLogger("app.guardrails.rate_limiter")


class RedisRateLimiter:
    """Sliding-window per-user/per-IP rate limiter, concurrent-stream cap, and abuse-score throttler."""

    def __init__(self, settings: GuardrailsSettings | None = None, redis_client: Any | None = None) -> None:
        self.settings = settings or get_guardrails_settings()
        self._redis = redis_client

    async def _client(self) -> Any:
        if self._redis is not None:
            return self._redis
        client = get_redis_client()
        if inspect.isawaitable(client):
            client = await client
        return client

    async def _check_sliding_window(self, r: Any, key: str, limit: int, window_sec: int = 60) -> tuple[bool, int]:
        now = time.time()
        cutoff = now - window_sec
        member = f"{now:.6f}:{uuid.uuid4().hex[:8]}"
        await r.zremrangebyscore(key, 0, cutoff)
        count = int(await r.zcard(key))
        if count >= limit:
            oldest = await r.zrange(key, 0, 0, withscores=True)
            retry_after = max(1, int(window_sec - (now - float(oldest[0][1])))) if oldest else window_sec
            return False, retry_after
        await r.zadd(key, {member: now})
        await r.expire(key, window_sec + 5)
        return True, 0

    async def check_and_acquire_stream(self, user_id: str | uuid.UUID, client_ip: str) -> None:
        """Enforce abuse throttle, per-user RPM, per-IP RPM, and concurrent stream cap."""
        uid = str(user_id)
        ip = (client_ip or "unknown").strip()
        try:
            r = await self._client()
            # 1. Check temporary abuse throttle
            abuse_ttl = int(await r.ttl(f"rl:throttle:{uid}") or -2)
            if abuse_ttl > 0:
                raise HTTPException(
                    status_code=429,
                    detail="Too many repeated guardrail/rate-limit violations. Please retry later.",
                    headers={"Retry-After": str(abuse_ttl)},
                )

            # 2. Per-IP sliding window
            ip_ok, ip_retry = await self._check_sliding_window(
                r, f"rl:ip:{ip}", self.settings.RATE_LIMIT_IP_RPM, window_sec=60
            )
            if not ip_ok:
                raise HTTPException(
                    status_code=429,
                    detail="IP rate limit exceeded.",
                    headers={"Retry-After": str(ip_retry)},
                )

            # 3. Per-user sliding window
            user_ok, user_retry = await self._check_sliding_window(
                r, f"rl:user:{uid}", self.settings.RATE_LIMIT_USER_RPM, window_sec=60
            )
            if not user_ok:
                await self.record_abuse_hit(uid, r=r)
                raise HTTPException(
                    status_code=429,
                    detail="User rate limit exceeded.",
                    headers={"Retry-After": str(user_retry)},
                )

            # 4. Concurrent stream cap per user
            conc_key = f"rl:conc:{uid}"
            current = int(await r.incr(conc_key))
            await r.expire(conc_key, int(self.settings.RATE_LIMIT_REQUEST_DEADLINE_SEC) + 10)
            if current > self.settings.RATE_LIMIT_USER_CONCURRENT_STREAMS:
                await r.decr(conc_key)
                raise HTTPException(
                    status_code=429,
                    detail="Too many concurrent chat streams for this user.",
                    headers={"Retry-After": "5"},
                )
        except HTTPException:
            raise
        except Exception as exc:
            if self.settings.RATE_LIMIT_FAIL_OPEN:
                logger.warning(
                    "RATE LIMITER WARNING: Redis unavailable (%s); failing open.",
                    type(exc).__name__,
                )
                return
            raise HTTPException(status_code=503, detail="Rate limiter unavailable.")

    async def release_stream(self, user_id: str | uuid.UUID) -> None:
        uid = str(user_id)
        try:
            r = await self._client()
            val = int(await r.decr(f"rl:conc:{uid}"))
            if val < 0:
                await r.set(f"rl:conc:{uid}", 0, ex=60)
        except Exception as exc:
            logger.warning("Failed to release stream slot in Redis (%s).", type(exc).__name__)

    async def record_abuse_hit(self, user_id: str | uuid.UUID, r: Any | None = None) -> None:
        uid = str(user_id)
        try:
            client = r or await self._client()
            score = int(await client.incr(f"rl:abuse:{uid}"))
            await client.expire(f"rl:abuse:{uid}", 300)
            if score >= 3:
                await client.set(f"rl:throttle:{uid}", "1", ex=60)
        except Exception:
            pass

    async def check_endpoint_limit(
        self,
        scope: str,
        identifier: str,
        limit_per_min: int = 5,
        window_sec: int = 60,
    ) -> None:
        """Enforce a per-identifier sliding-window rate limit for auth or audio endpoints."""
        ident = (identifier or "unknown").strip()
        try:
            r = await self._client()
            ok, retry_after = await self._check_sliding_window(
                r,
                f"rl:{scope}:{ident}",
                limit_per_min,
                window_sec=window_sec,
            )
            if not ok:
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded. Please wait before trying again.",
                    headers={"Retry-After": str(retry_after)},
                )
        except HTTPException:
            raise
        except Exception as exc:
            if self.settings.RATE_LIMIT_FAIL_OPEN:
                logger.warning(
                    "RATE LIMITER WARNING: Redis unavailable (%s); failing open.",
                    type(exc).__name__,
                )
                return
            raise HTTPException(status_code=503, detail="Rate limiter unavailable.")
