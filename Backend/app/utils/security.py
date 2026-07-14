"""
app/utils/security.py

Thin adapter layer — delegates to app.core.security.

This module exists for backward compatibility with code that imports
password utilities and token helpers from app.utils.security.

All logic lives in app.core.security. Do not add new implementations here.
"""

from datetime import timedelta, timezone, datetime
from typing import Any, Optional, Union

from app.core.config import settings
from app.core.security import (
    create_access_token as _create_access_token,
    decode_token,
    generate_secure_token,
    get_password_hash,
    verify_password,
)


# ─────────────────────────────────────────────────────────────────────────────
# RE-EXPORTS (imported by crud_user, auth_password, etc.)
# ─────────────────────────────────────────────────────────────────────────────

__all__ = [
    "get_password_hash",
    "verify_password",
    "create_access_token",
    "generate_password_reset_token",
    "verify_password_reset_token",
]


def create_access_token(
    subject: Union[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Wrapper kept for routes that import from app.utils.security.
    Delegates to app.core.security.create_access_token.
    """
    return _create_access_token(subject=subject, expires_delta=expires_delta)


def generate_password_reset_token(email: str) -> str:
    """
    Issue a short-lived token for password-reset flows.

    The token encodes the email in a signed JWT valid for
    EMAIL_RESET_TOKEN_EXPIRE_HOURS hours.
    """
    from jose import jwt as _jwt

    now = datetime.now(timezone.utc)                    # ← was datetime.utcnow() (deprecated)
    expire = now + timedelta(hours=settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS)

    payload = {
        "sub": email,
        "type": "password_reset",
        "nbf": now,
        "iat": now,
        "exp": expire,
    }

    return _jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_password_reset_token(token: str) -> Optional[str]:
    """
    Decode a password-reset token.

    Returns the email address (sub claim) on success, None otherwise.
    Only tokens with type == "password_reset" are accepted.
    """
    payload = decode_token(token)
    if not payload:
        return None
    if payload.get("type") != "password_reset":
        return None
    return payload.get("sub")
