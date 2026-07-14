"""
app/core/rate_limiter.py

Redis-backed rate limiting as a FastAPI dependency.

Usage — add to any route:

    from app.core.rate_limiter import RateLimiter, otp_request_limiter

    @router.post("/login")
    def login(
        ...,
        _: None = Depends(otp_request_limiter),
    ):
        ...

Each limit is keyed by (prefix, client_ip) so limits are independent
per route — a burst on /login does not consume the budget for /verify-otp.

Falls back to an in-memory sliding-window store if Redis is unavailable.
The in-memory store is NOT shared across worker processes.
"""

import logging
import time
from collections import defaultdict
from typing import Optional

from fastapi import HTTPException, Request, status

from app.core.redis_client import redis_available, redis_client

logger = logging.getLogger(__name__)

_memory_store: dict[str, list[float]] = defaultdict(list)


class RateLimiter:
    """
    Sliding-window rate limiter as a FastAPI dependency.

    Args:
        times:      Max requests allowed within the window.
        seconds:    Window duration in seconds.
        key_prefix: Namespace prefix for Redis keys.
    """

    def __init__(self, times: int, seconds: int, key_prefix: Optional[str] = None) -> None:
        if times <= 0 or seconds <= 0:
            raise ValueError("times and seconds must be positive")
        self.times = times
        self.seconds = seconds
        self.key_prefix = key_prefix

    async def __call__(self, request: Request) -> None:
        client_ip = (
            request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or (request.client.host if request.client else "unknown")
        )
        prefix = self.key_prefix or request.url.path.replace("/", ":")
        key = f"rl:{prefix}:{client_ip}"

        if redis_available():
            self._check_redis(key)
        else:
            self._check_memory(key, client_ip)

    def _check_redis(self, key: str) -> None:
        now = time.time()
        window_start = now - self.seconds
        try:
            pipe = redis_client.pipeline()
            pipe.zremrangebyscore(key, "-inf", window_start)
            pipe.zcard(key)
            pipe.zadd(key, {str(now): now})
            pipe.expire(key, self.seconds + 1)
            results = pipe.execute()
            count: int = results[1]
            if count >= self.times:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests. Please slow down.",
                    headers={"Retry-After": str(self.seconds)},
                )
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("Redis rate-limit check failed, allowing through: %s", exc)

    def _check_memory(self, key: str, client_ip: str) -> None:
        now = time.time()
        window_start = now - self.seconds
        _memory_store[key] = [t for t in _memory_store[key] if t > window_start]
        if len(_memory_store[key]) >= self.times:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please slow down.",
                headers={"Retry-After": str(self.seconds)},
            )
        _memory_store[key].append(now)


# ── Pre-built limiters ────────────────────────────────────────────────────────

# OTP send: 5 attempts per 10 minutes per IP
otp_request_limiter = RateLimiter(times=5, seconds=600, key_prefix="auth:otp_request")

# OTP verify: 10 attempts per 10 minutes per IP
otp_verify_limiter = RateLimiter(times=10, seconds=600, key_prefix="auth:otp_verify")

# Token refresh: 60 per 15 minutes per IP
refresh_limiter = RateLimiter(times=60, seconds=900, key_prefix="auth:refresh")

# General login initiation: 20 per minute per IP
login_limiter = RateLimiter(times=20, seconds=60, key_prefix="auth:login")
