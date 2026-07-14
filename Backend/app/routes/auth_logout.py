"""
app/routes/auth_logout.py

POST /auth/logout      — revoke one device session.
POST /auth/logout-all  — revoke all sessions for the authenticated user.

Both endpoints:
  - Immediately JTI-deny the current access token (from Authorization header).
  - Clear the HttpOnly refresh-token cookie and the CSRF cookie.
  - Return 200 regardless of whether the session was found in the DB
    (prevents enumeration of valid/invalid tokens).

Structured log fields (no PII — only IDs and IPs):
  auth.logout.single   user_id, ip
  auth.logout.all      user_id, session_count, ip
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.csrf import clear_csrf_cookie
from app.core.database import get_db
from app.core.security import decode_access_token
from app.core.token_store import revoke_jti, set_revoke_before
from app.models.active_session import ActiveSession
from app.models.user import User
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Authentication"])


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _jti_deny_from_bearer(request: Request) -> None:
    """Add the current access token's JTI to the Redis deny-list."""
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return
    token = header.split(" ", 1)[1]
    payload = decode_access_token(token)
    jti    = payload.get("jti")
    exp_ts = payload.get("exp")
    if jti and exp_ts:
        expires_at = datetime.fromtimestamp(exp_ts, tz=timezone.utc)
        revoke_jti(jti, expires_at)


def _clear_auth_cookies(response: Response) -> None:
    """Delete both the refresh token and CSRF cookies."""
    response.delete_cookie(
        key="am_refresh_token",
        path="/",
        domain=settings.COOKIE_DOMAIN or None,
    )
    clear_csrf_cookie(response)


# ─────────────────────────────────────────────────────────────────────────────
# POST /auth/logout
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/logout")
def logout(
    request:  Request,
    response: Response,
    db:       Session = Depends(get_db),
    am_refresh_token: Optional[str] = Cookie(default=None),
):
    """
    Revoke the session for this device.

    The refresh token is read from the HttpOnly cookie (browser clients).
    Mobile clients may omit the cookie — the JTI revocation of the access
    token still takes effect.

    Always returns 200 — the response body does not reveal whether the
    session existed.
    """
    client_ip = request.client.host if request.client else "unknown"

    # Revoke refresh token session in DB (cookie path)
    if am_refresh_token:
        session = (
            db.query(ActiveSession)
            .filter(
                ActiveSession.refresh_token == am_refresh_token,
                ActiveSession.is_revoked == False,  # noqa: E712
            )
            .first()
        )
        if session:
            session.is_revoked = True
            db.commit()
            logger.info("auth.logout.single user_id=%s ip=%s", session.user_id, client_ip)

    # Immediately deny the current access token
    _jti_deny_from_bearer(request)

    # Clear cookies on the response
    _clear_auth_cookies(response)

    return {"success": True, "message": "Logged out successfully."}


# ─────────────────────────────────────────────────────────────────────────────
# POST /auth/logout-all
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/logout-all")
def logout_all_devices(
    request:      Request,
    response:     Response,
    current_user: User = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    Revoke every session for the authenticated user across all devices.

    Uses two mechanisms:
      1. DB: marks all ActiveSession rows is_revoked=True.
      2. Redis: sets a per-user revoke-before timestamp so outstanding
         access tokens (which won't have a DB entry) are also rejected
         immediately — even within their 15-minute natural lifetime.
    """
    client_ip = request.client.host if request.client else "unknown"

    revoked_count = (
        db.query(ActiveSession)
        .filter(
            ActiveSession.user_id == current_user.id,
            ActiveSession.is_revoked == False,  # noqa: E712
        )
        .update({"is_revoked": True})
    )
    db.commit()

    # Redis: invalidate all currently live access tokens for this user
    set_revoke_before(current_user.id)

    # JTI-deny the access token on this specific request too
    _jti_deny_from_bearer(request)

    # Clear auth cookies on this device
    _clear_auth_cookies(response)

    logger.info(
        "auth.logout.all user_id=%s session_count=%d ip=%s",
        current_user.id, revoked_count, client_ip,
    )

    return {
        "success": True,
        "message": f"Logged out from {revoked_count} device(s) successfully.",
    }
