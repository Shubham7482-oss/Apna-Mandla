"""
app/core/redis_client.py

Redis connection singleton.

Usage:
    from app.core.redis_client import redis_client, redis_available

    if redis_available():
        redis_client.set("key", "value", ex=60)

In environments without Redis (CI, simple local dev), all operations that
require Redis should check redis_available() and degrade gracefully rather
than crashing.
"""

import logging

import redis
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.config import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# CLIENT
# ─────────────────────────────────────────────────────────────────────────────

redis_client: redis.Redis = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    password=settings.REDIS_PASSWORD,
    decode_responses=True,
    socket_connect_timeout=2,    # fail fast on startup if Redis is not running
    socket_timeout=2,
)

# ─────────────────────────────────────────────────────────────────────────────
# HEALTH PROBE
# ─────────────────────────────────────────────────────────────────────────────

_redis_ok: bool | None = None  # cached on first check


def redis_available() -> bool:
    """
    Returns True if Redis is reachable.

    Result is cached after the first successful ping so that subsequent
    calls do not incur a network round-trip.  Failure is NOT cached —
    callers can retry after a transient outage.
    """
    global _redis_ok
    if _redis_ok is True:
        return True
    try:
        redis_client.ping()
        _redis_ok = True
        return True
    except (RedisConnectionError, Exception) as exc:
        logger.warning("Redis unavailable: %s", exc)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# STARTUP CHECK
# ─────────────────────────────────────────────────────────────────────────────

def _startup_probe() -> None:
    if redis_available():
        logger.info(
            "Redis connected: %s:%s db=%s",
            settings.REDIS_HOST,
            settings.REDIS_PORT,
            settings.REDIS_DB,
        )
    else:
        logger.warning(
            "Redis not reachable at %s:%s — rate limiting and OTP throttle "
            "will fall back to in-memory store. This is NOT suitable for "
            "multi-process production deployments.",
            settings.REDIS_HOST,
            settings.REDIS_PORT,
        )


_startup_probe()
