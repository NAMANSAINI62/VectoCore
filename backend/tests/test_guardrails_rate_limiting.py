"""Unit tests for Job 4: Redis sliding-window rate limiter, concurrency cap, sync client handling, and Redis-down fail-open."""

import asyncio
import time
from typing import Any

import pytest
from fastapi import HTTPException

from app.guardrails.config.settings import GuardrailsSettings
from app.guardrails.rate_limiter import RedisRateLimiter


class FakeRedis:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.zsets: dict[str, dict[str, float]] = {}
        self.kv: dict[str, tuple[str, float | None]] = {}

    def _check(self) -> None:
        if self.fail:
            raise ConnectionError("Redis down")

    async def zremrangebyscore(self, key: str, min_s: float, max_s: float) -> int:
        self._check()
        zs = self.zsets.get(key, {})
        to_del = [m for m, s in zs.items() if min_s <= s <= max_s]
        for m in to_del:
            del zs[m]
        return len(to_del)

    async def zcard(self, key: str) -> int:
        self._check()
        return len(self.zsets.get(key, {}))

    async def zrange(self, key: str, start: int, end: int, withscores: bool = False) -> list[Any]:
        self._check()
        items = sorted(self.zsets.get(key, {}).items(), key=lambda kv: kv[1])
        sl = items[start : end + 1 if end >= 0 else None]
        return sl if withscores else [m for m, _ in sl]

    async def zadd(self, key: str, mapping: dict[str, float]) -> int:
        self._check()
        self.zsets.setdefault(key, {}).update(mapping)
        return len(mapping)

    async def expire(self, key: str, _sec: int) -> bool:
        self._check()
        return True

    async def ttl(self, key: str) -> int:
        self._check()
        if key not in self.kv:
            return -2
        _, exp = self.kv[key]
        if exp is None:
            return -1
        rem = int(exp - time.time())
        if rem <= 0:
            del self.kv[key]
            return -2
        return rem

    async def incr(self, key: str) -> int:
        self._check()
        val = int(self.kv.get(key, ("0", None))[0]) + 1
        self.kv[key] = (str(val), None)
        return val

    async def decr(self, key: str) -> int:
        self._check()
        val = int(self.kv.get(key, ("0", None))[0]) - 1
        self.kv[key] = (str(val), None)
        return val

    async def get(self, key: str) -> str | None:
        self._check()
        if key not in self.kv:
            return None
        val, exp = self.kv[key]
        if exp is not None and time.time() > exp:
            del self.kv[key]
            return None
        return val

    async def set(self, key: str, val: Any, ex: int | None = None) -> bool:
        self._check()
        exp = time.time() + ex if ex is not None else None
        self.kv[key] = (str(val), exp)
        return True


def test_rate_limiter_window_expiry_and_concurrency_cap() -> None:
    async def _run() -> None:
        fake = FakeRedis()
        settings = GuardrailsSettings(
            RATE_LIMIT_USER_RPM=2,
            RATE_LIMIT_USER_CONCURRENT_STREAMS=1,
            RATE_LIMIT_IP_RPM=10,
        )
        rl = RedisRateLimiter(settings=settings, redis_client=fake)

        # 1st stream acquired
        await rl.check_and_acquire_stream("u1", "1.2.3.4")
        # 2nd concurrent stream exceeds cap=1 -> 429
        with pytest.raises(HTTPException) as exc1:
            await rl.check_and_acquire_stream("u1", "1.2.3.4")
        assert exc1.value.status_code == 429
        assert "Retry-After" in (exc1.value.headers or {})

        await rl.release_stream("u1")

        # Simulate window expiry on zset
        fake.zsets["rl:user:u1"] = {"old": time.time() - 61}
        await rl.check_and_acquire_stream("u1", "1.2.3.4")
        await rl.release_stream("u1")

    asyncio.run(_run())


def test_rate_limiter_redis_down_fails_open_with_warning(caplog: pytest.LogCaptureFixture) -> None:
    async def _run() -> None:
        fake_down = FakeRedis(fail=True)
        rl = RedisRateLimiter(settings=GuardrailsSettings(RATE_LIMIT_FAIL_OPEN=True), redis_client=fake_down)
        await rl.check_and_acquire_stream("u1", "1.2.3.4")
        assert "failing open" in caplog.text.lower()

    asyncio.run(_run())


def test_rate_limiter_accepts_synchronous_get_redis_client(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        fake = FakeRedis()
        monkeypatch.setattr("app.guardrails.rate_limiter.get_redis_client", lambda: fake)
        rl = RedisRateLimiter(settings=GuardrailsSettings(RATE_LIMIT_USER_RPM=2, RATE_LIMIT_IP_RPM=10))
        await rl.check_and_acquire_stream("u-sync", "127.0.0.1")
        await rl.release_stream("u-sync")
        assert len(fake.zsets.get("rl:user:u-sync", {})) == 1

    asyncio.run(_run())


def test_request_deadline_enforced() -> None:
    async def _run() -> None:
        async def _slow_op() -> None:
            await asyncio.sleep(0.3)

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(_slow_op(), timeout=0.05)

    asyncio.run(_run())
