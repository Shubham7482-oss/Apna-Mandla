"""
app/core/token_store.py

Redis-backed token revocation store.

Two mechanisms work together:

1. JTI deny-list  (per-token, fine-grained)
   ─────────────────────────────────────────
   When a specific access token must be invalidated immediately (e.g. single-
   device logout), its `jti` claim is written to Redis with a TTL equal to
   the token's remaining lifetime.  Once the token expires naturally, the
   Redis key expires with it — no manual cleanup needed.

   Key pattern:  token:deny:jti:{jti}
   TTL:          remaining seconds until token expiry

2. Revoke-before timestamp  (per-user, bulk logout)
   ─────────────────────────────────────────────────
   When logout-all is triggered, a UTC timestamp is stored for the user.
   Any access token issued BEFORE that timestamp is rejected, even if its
   JTI is not in the deny-list.  This invalidates every live access token
   for the user in one Redis write instead of N deny-list entries.

   Key pattern:  token:revoke_before:{user_id}
   TTL:          ACCESS_TOKEN_EXPIRE_MINUTES * 60  (max possible token age)

In-memory fallback
──────────────────
If Redis is unavailable, both mechanisms degrade to an in-memory dict.
This is safe for single-process dev but NOT suitable for multi-process
or multi-instance production deployments.  Always run Redis in production.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from app.core.config import settings
from app.core.redis_client import redis_available, redis_client

logger = logging.getLogger(__name__)

# In-memory fallback stores (single-process only)
_jti_deny: dict[str, float] = {}         # jti → expiry unix timestamp
_revoke_before: dict[int, float] = {}    # user_id → revoke_before unix timestamp

# ─────────────────────────────────────────────────────────────────────────────
# JTI DENY-LIST
# ─────────────────────────────────────────────────────────────────────────────

def revoke_jti(jti: str, expires_at: datetime) -> None:
    """
    Add a JTI to the deny-list until it expires naturally.

    Args:
        jti:        The `jti` claim from the token payload.
        expires_at: The `exp` claim as a timezone-aware datetime.
    """
    now = datetime.now(timezone.utc)
    ttl_seconds = max(int((expires_at - now).total_seconds()), 1)
    key = f"token:deny:jti:{jti}"

    if redis_available():
        try:
            redis_client.setex(key, ttl_seconds, "1")
            return
        except Exception as exc:
            logger.warning("Redis JTI deny write failed, falling back to memory: %s", exc)

    # Memory fallback
    _jti_deny[jti] = time.time() + ttl_seconds
    _cleanup_jti_memory()


def is_jti_revoked(jti: str) -> bool:
    """
    Return True if the JTI is on the deny-list.
    """
    key = f"token:deny:jti:{jti}"

    if redis_available():
        try:
            return bool(redis_client.exists(key))
        except Exception as exc:
            logger.warning("Redis JTI deny read failed, falling back to memory: %s", exc)

    # Memory fallback
    exp = _jti_deny.get(jti)
    if exp is None:
        return False
    if time.time() > exp:
        _jti_deny.pop(jti, None)
        return False
    return True


def _cleanup_jti_memory() -> None:
    """Evict expired entries from the in-memory fallback (called on every write)."""
    now = time.time()
    expired = [k for k, v in _jti_deny.items() if v < now]
    for k in expired:
        del _jti_deny[k]


# ─────────────────────────────────────────────────────────────────────────────
# PER-USER REVOKE-BEFORE TIMESTAMP
# ─────────────────────────────────────────────────────────────────────────────

def set_revoke_before(user_id: int) -> None:
    """
    Record the current UTC timestamp for this user.

    Any access token whose `iat` (issued-at) is earlier than this value
    will be rejected, even if its JTI is not explicitly denied.

    TTL is set to the maximum possible access token lifetime so the key
    expires automatically once all live tokens have expired.
    """
    now_ts = int(time.time())
    ttl = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    key = f"token:revoke_before:{user_id}"

    if redis_available():
        try:
            redis_client.setex(key, ttl, str(now_ts))
            return
        except Exception as exc:
            logger.warning("Redis revoke_before write failed, falling back to memory: %s", exc)

    _revoke_before[user_id] = float(now_ts)


def get_revoke_before(user_id: int) -> Optional[float]:
    """
    Return the revoke-before timestamp for a user, or None if not set.
    """
    key = f"token:revoke_before:{user_id}"

    if redis_available():
        try:
            val = redis_client.get(key)
            return float(val) if val else None
        except Exception as exc:
            logger.warning("Redis revoke_before read failed, falling back to memory: %s", exc)

    return _revoke_before.get(user_id)


# ─────────────────────────────────────────────────────────────────────────────
# COMPOSITE CHECK — used by get_current_user
# ─────────────────────────────────────────────────────────────────────────────

def is_access_token_revoked(payload: dict) -> bool:
    """
    Return True if the decoded access token payload should be rejected.

    Checks (in order, cheapest first):
      1. JTI deny-list  — catches single-device logout.
      2. Revoke-before  — catches logout-all / password change.
    """
    jti: Optional[str] = payload.get("jti")
    if jti and is_jti_revoked(jti):
        return True

    try:
        user_id = int(payload.get("sub", 0))
    except (ValueError, TypeError):
        return False

    revoke_ts = get_revoke_before(user_id)
    if revoke_ts is not None:
        iat: Optional[int] = payload.get("iat")
        if iat is not None and iat < revoke_ts:
            return True

    return False
