"""
app/routes/auth_refresh.py

POST /auth/refresh  — silent token rotation.

Token source priority:
  1. HttpOnly cookie  `am_refresh_token`  (preferred — JS cannot read it)
  2. Request body     `{ "refresh_token": "..." }` (fallback for non-browser
     clients such as mobile apps that cannot use cookies)

CSRF protection:
  When the token comes from the cookie, the X-CSRF-Token header is required
  and must match the `am_csrf_token` readable cookie (double-submit pattern).
  When the token comes from the body, CSRF is not applicable (the caller
  already possesses the token value explicitly).

Rotation:
  - Old session is immediately revoked in active_sessions.
  - New session is inserted with a fresh refresh token.
  - If a revoked token is replayed, ALL sessions for that user are wiped
    and a security warning is logged.

Response:
  HTTP 200
  Set-Cookie: am_refresh_token=<new_jwt>; HttpOnly; Secure; SameSite=Strict
  Set-Cookie: am_csrf_token=<new_random>; Secure; SameSite=Strict
  { "access_token": "<jwt>", "token_type": "bearer" }

The new refresh token is NOT echoed in the JSON body — it lives in the
HttpOnly cookie only.  This prevents JS-based exfiltration.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.csrf import generate_csrf_token, require_csrf_token, set_csrf_cookie
from app.core.database import get_db
from app.core.rate_limiter import refresh_limiter
from app.core.security import create_token_pair, decode_refresh_token
from app.models.active_session import ActiveSession
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Authentication"])

_INVALID = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired refresh token.",
    headers={"WWW-Authenticate": "Bearer"},
)


class RefreshRequest(BaseModel):
    """Optional body — only used by non-browser (mobile) clients."""
    refresh_token: Optional[str] = None


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key="am_refresh_token",
        value=refresh_token,
        httponly=settings.COOKIE_HTTPONLY_REFRESH,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        domain=settings.COOKIE_DOMAIN or None,
        path="/",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key="am_refresh_token",
        path="/",
        domain=settings.COOKIE_DOMAIN or None,
    )


@router.post("/refresh")
def refresh_access_token(
    request:  Request,
    response: Response,
    db:       Session = Depends(get_db),
    _rate:    None = Depends(refresh_limiter),
    # Cookie source (browser clients)
    am_refresh_token: Optional[str] = Cookie(default=None),
    # Body schema (mobile clients — body is optional so cookie path still works)
    body: RefreshRequest = Depends(),
):
    """
    Issue a new access token by presenting a valid refresh token.

    Browser clients: token comes from the HttpOnly cookie automatically.
    Mobile clients:  token sent in the JSON body.
    """
    client_ip  = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("User-Agent", "")

    # ── 1. Resolve the refresh token ──────────────────────────────────────────
    using_cookie = False
    if am_refresh_token:
        # Browser path — validate CSRF before touching anything else.
        using_cookie = True
        try:
            require_csrf_token(
                x_csrf_token=request.headers.get("X-CSRF-Token"),
                am_csrf_token=request.cookies.get("am_csrf_token"),
            )
        except HTTPException:
            logger.warning("auth.refresh.csrf_fail ip=%s", client_ip)
            raise
        raw_token = am_refresh_token
    elif body.refresh_token:
        # Mobile / API client path — body-supplied token, no CSRF needed.
        raw_token = body.refresh_token
    else:
        logger.warning("auth.refresh.no_token ip=%s", client_ip)
        raise _INVALID

    # ── 2. Decode JWT ─────────────────────────────────────────────────────────
    payload = decode_refresh_token(raw_token)
    if not payload:
        logger.warning("auth.refresh.invalid_jwt ip=%s cookie=%s", client_ip, using_cookie)
        if using_cookie:
            _clear_refresh_cookie(response)
        raise _INVALID

    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise _INVALID

    # ── 3. Validate session ───────────────────────────────────────────────────
    session = (
        db.query(ActiveSession)
        .filter(
            ActiveSession.refresh_token == raw_token,
            ActiveSession.user_id == user_id,
            ActiveSession.is_revoked == False,  # noqa: E712
        )
        .first()
    )

    if not session:
        # Revoked token presented — possible theft; nuke all sessions.
        logger.warning(
            "auth.refresh.token_reuse user_id=%s ip=%s — revoking all sessions",
            user_id, client_ip,
        )
        db.query(ActiveSession).filter(
            ActiveSession.user_id == user_id
        ).update({"is_revoked": True})
        db.commit()
        if using_cookie:
            _clear_refresh_cookie(response)
        raise _INVALID

    # ── 4. User still active ──────────────────────────────────────────────────
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        session.is_revoked = True
        db.commit()
        if using_cookie:
            _clear_refresh_cookie(response)
        raise _INVALID

    # ── 5. Rotate ─────────────────────────────────────────────────────────────
    session.is_revoked = True
    tokens = create_token_pair(subject=str(user_id))

    db.add(ActiveSession(
        user_id=user_id,
        refresh_token=tokens.refresh_token,
        ip_address=client_ip,
        user_agent=user_agent[:512],
        is_revoked=False,
    ))
    db.commit()

    # ── 6. Set new cookies ────────────────────────────────────────────────────
    _set_refresh_cookie(response, tokens.refresh_token)
    new_csrf = generate_csrf_token()
    set_csrf_cookie(response, new_csrf)

    logger.info("auth.refresh.success user_id=%s ip=%s cookie=%s", user_id, client_ip, using_cookie)

    # Return only the access token in the body.
    # The new refresh token is delivered via the HttpOnly cookie above.
    return {
        "access_token": tokens.access_token,
        "token_type":   tokens.token_type,
    }
