"""
app/core/csrf.py

Double-submit cookie CSRF protection.

Pattern:
  1. On login/token-issue: generate a random CSRF token.
  2. Set it as a READABLE (non-httpOnly) cookie so JavaScript can access it.
  3. On state-changing requests that use the HttpOnly refresh cookie
     (currently: POST /auth/refresh), the frontend must read this cookie
     value and send it as the `X-CSRF-Token` header.
  4. This endpoint dependency validates that the header value equals the
     cookie value.  A cross-site attacker cannot read the cookie value
     due to the same-origin policy, so they cannot forge the header.

Why this is safe:
  - The HttpOnly refresh-token cookie is immune to XSS (JS cannot read it).
  - The CSRF cookie IS readable by JS but only by same-origin JS.
  - A CSRF attacker on another origin cannot read document.cookie from
    this origin, so they cannot reproduce the header value.
  - SameSite=Strict on the refresh cookie adds a second layer of defence.

Scope:
  - CSRF protection is only needed for endpoints that rely on automatic
    cookie inclusion (the /refresh endpoint that reads the HttpOnly cookie).
  - Regular API calls that use the Authorization: Bearer header are NOT
    subject to CSRF because the browser never auto-adds that header.
"""

import secrets
import hmac
from typing import Optional

from fastapi import Cookie, Header, HTTPException, Response, status

from app.core.config import settings

CSRF_COOKIE_NAME  = "am_csrf_token"
CSRF_HEADER_NAME  = "X-CSRF-Token"  # FastAPI converts to x_csrf_token param


def generate_csrf_token() -> str:
    """Generate a cryptographically random CSRF token (URL-safe, 32 bytes)."""
    return secrets.token_urlsafe(32)


def set_csrf_cookie(response: Response, token: str) -> None:
    """
    Attach the CSRF token as a readable (non-httpOnly) cookie.

    JavaScript on the same origin reads this value and echoes it
    as the X-CSRF-Token header on requests to protected endpoints.
    """
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        httponly=False,                           # JS must be able to read this
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        domain=settings.COOKIE_DOMAIN or None,
        path="/",
    )


def clear_csrf_cookie(response: Response) -> None:
    """Remove the CSRF cookie (called on logout)."""
    response.delete_cookie(
        key=CSRF_COOKIE_NAME,
        path="/",
        domain=settings.COOKIE_DOMAIN or None,
    )


def require_csrf_token(
    x_csrf_token: Optional[str] = Header(default=None, alias="X-CSRF-Token"),
    am_csrf_token: Optional[str] = Cookie(default=None),
) -> None:
    """
    FastAPI dependency — validates the CSRF double-submit.

    Raises HTTP 403 if:
      - Either the header or the cookie is missing.
      - The values do not match (constant-time comparison).

    Usage:
        @router.post("/refresh")
        def refresh(_: None = Depends(require_csrf_token), ...):
            ...
    """
    if not x_csrf_token or not am_csrf_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token missing. Include the X-CSRF-Token header.",
        )
    # Constant-time comparison prevents timing oracle on the token value.
    if not hmac.compare_digest(x_csrf_token, am_csrf_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token mismatch.",
        )
