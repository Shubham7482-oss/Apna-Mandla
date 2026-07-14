"""
app/core/security.py

Low-level cryptographic primitives for Apna Mandla.

Responsibilities:
  - Password hashing / verification        (bcrypt via passlib)
  - JWT creation / decoding                (python-jose)
  - OTP generation / hashing / verification (SHA-256 + HMAC)
  - Secure token generation                (secrets module)

All public functions in this module are imported by routes and services.
Do NOT add business logic here.
"""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# ─────────────────────────────────────────────────────────────────────────────
# PASSWORD HASHING
# ─────────────────────────────────────────────────────────────────────────────

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    # Increase bcrypt rounds in production if your hardware allows.
    # Default is 12; do not go below 10.
)

# bcrypt silently truncates at 72 BYTES (not characters).
# For ASCII passwords this is 72 chars; for multibyte Unicode it is fewer.
# We SHA-256 pre-hash to a fixed 64-char hex string before bcrypt so that:
#   1. All Unicode passwords are handled safely.
#   2. The input to bcrypt is always exactly 64 bytes (well within 72).
#   3. Password length is not leaked through timing.
#
# WARNING: This changes the stored hash format. Existing hashes produced by
# the old password[:72] approach will NOT verify against the new scheme.
# Run a migration script if you have existing users.
_PEPPER: str = settings.SECRET_KEY[:16]  # 16 chars of SECRET_KEY as static pepper


def _prehash_password(password: str) -> str:
    """
    HMAC-SHA256 pre-hash before bcrypt.
    Uses the first 16 chars of SECRET_KEY as a static pepper so that
    a database leak alone cannot crack passwords via rainbow tables.
    """
    return hmac.new(
        _PEPPER.encode("utf-8"),
        password.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()  # 64 hex chars = 64 bytes — safe for bcrypt


def get_password_hash(password: str) -> str:
    return pwd_context.hash(_prehash_password(password))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(_prehash_password(plain_password), hashed_password)


# ─────────────────────────────────────────────────────────────────────────────
# JWT — ACCESS & REFRESH TOKENS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TokenPair:
    """Returned by create_token_pair() — both tokens issued together."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


def create_access_token(
    subject: str | Any,
    is_admin: bool = False,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Issue a short-lived access token.

    Claims:
        sub   — user ID (string)
        type  — "access" (enforced by get_current_user to prevent refresh reuse)
        jti   — unique token ID (enables per-token revocation if stored)
        iss   — issuer (project name)
        iat   — issued-at (UTC)
        exp   — expiry (UTC)
        is_admin — whether the subject is an admin user
    """
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    payload = {
        "sub": str(subject),
        "type": "access",
        "jti": secrets.token_hex(16),   # unique per token for revocation support
        "iss": settings.PROJECT_NAME,
        "is_admin": is_admin,
        "iat": now,
        "exp": expire,
    }

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(
    subject: str | Any,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Issue a long-lived refresh token.

    The full JWT string is stored in active_sessions so it can be revoked
    server-side via the is_revoked flag.

    Claims:
        sub   — user ID (string)
        type  — "refresh" (prevents use as an access token)
        jti   — unique token ID
        iss   — issuer
        iat   — issued-at
        exp   — expiry
    """
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )

    payload = {
        "sub": str(subject),
        "type": "refresh",
        "jti": secrets.token_hex(16),
        "iss": settings.PROJECT_NAME,
        "iat": now,
        "exp": expire,
    }

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_token_pair(
    subject: str | Any,
    is_admin: bool = False,
) -> TokenPair:
    """
    Issue both tokens in one call.
    Preferred entry-point in auth routes: avoids calling create_* twice.
    """
    return TokenPair(
        access_token=create_access_token(subject, is_admin=is_admin),
        refresh_token=create_refresh_token(subject),
    )


# ─────────────────────────────────────────────────────────────────────────────
# TOKEN DECODING
# ─────────────────────────────────────────────────────────────────────────────

class TokenError(Exception):
    """Raised when a token cannot be decoded or fails type validation."""

    EXPIRED = "TOKEN_EXPIRED"
    INVALID = "TOKEN_INVALID"
    WRONG_TYPE = "TOKEN_WRONG_TYPE"

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT signature + expiry.

    Returns the payload dict on success.
    Returns {} on any failure (backward-compatible behaviour).

    For structured error handling use decode_access_token / decode_refresh_token.
    """
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
    except (JWTError, Exception):
        return {}


def _decode_token_strict(token: str) -> dict:
    """
    Internal strict decoder that raises TokenError with a reason code.
    Used by decode_access_token and decode_refresh_token.
    """
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
    except ExpiredSignatureError:
        raise TokenError(TokenError.EXPIRED)
    except JWTError:
        raise TokenError(TokenError.INVALID)


def decode_access_token(token: str) -> dict:
    """
    Decode and validate an access token.

    Returns the payload dict.
    Returns {} if the token is invalid, expired, or has the wrong type.
    Callers that need the error reason should catch TokenError from
    _decode_token_strict directly.
    """
    payload = decode_token(token)
    if not payload:
        return {}
    if payload.get("type") != "access":
        return {}
    return payload


def decode_refresh_token(token: str) -> dict:
    """
    Decode and validate a refresh token.

    Returns the payload dict.
    Returns {} if the token is invalid, expired, or has the wrong type.
    """
    payload = decode_token(token)
    if not payload:
        return {}
    if payload.get("type") != "refresh":
        return {}
    return payload


# ─────────────────────────────────────────────────────────────────────────────
# OTP
# ─────────────────────────────────────────────────────────────────────────────

def generate_otp(length: int = 6) -> str:
    """Cryptographically secure OTP using secrets.randbelow (not random.randint)."""
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


def hash_otp(otp: str) -> str:
    """
    SHA-256 hash of the OTP.

    SHA-256 is appropriate here because:
      - OTPs are short-lived (≤10 minutes) and single-use
      - OTPs are 6 digits (≥10^6 space) — not brute-forceable within expiry
      - bcrypt's cost factor is wasted computation for short-lived secrets
    """
    return hashlib.sha256(otp.encode("utf-8")).hexdigest()


def verify_otp(plain_otp: str, hashed_otp: str) -> bool:
    """
    Constant-time OTP comparison to prevent timing attacks.
    Uses hmac.compare_digest on the SHA-256 digests.
    """
    return hmac.compare_digest(
        hashlib.sha256(plain_otp.encode("utf-8")).hexdigest(),
        hashed_otp,
    )


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def generate_secure_token(length: int = 32) -> str:
    """URL-safe random token for password-reset links, API keys, etc."""
    return secrets.token_urlsafe(length)


def now_utc() -> datetime:
    """Timezone-aware UTC now. Use this everywhere instead of datetime.utcnow()."""
    return datetime.now(timezone.utc)
