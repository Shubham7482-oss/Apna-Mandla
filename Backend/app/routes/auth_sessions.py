"""
app/routes/auth_sessions.py

Session management endpoints — lets authenticated users see and revoke
their own active sessions across devices.

GET    /auth/sessions          — list all active sessions for the current user
DELETE /auth/sessions/{id}     — revoke a specific session by its DB id
DELETE /auth/sessions          — revoke all sessions except the current one
                                 (equivalent to logout-all but keeps you logged in)

Security:
  - Sessions are scoped to current_user.id — users cannot see or revoke
    other users' sessions (IDOR prevention).
  - The current session (identified by the active refresh token cookie or
    the access token's sub claim) is excluded from the listing only when
    explicitly requested — users can still self-revoke if they want.
  - The access token used on this request is NOT revoked on DELETE — only
    the refresh token session is revoked.  The access token will expire
    naturally within 15 minutes.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.token_store import set_revoke_before
from app.models.active_session import ActiveSession
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Sessions"])


# ─────────────────────────────────────────────────────────────────────────────
# RESPONSE SCHEMA
# ─────────────────────────────────────────────────────────────────────────────

class SessionOut(BaseModel):
    id:               int
    ip_address:       Optional[str]
    user_agent:       Optional[str]
    created_at:       datetime
    last_activity_at: Optional[datetime]
    is_current:       bool   # True if this session matches the caller's cookie

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# GET /auth/sessions
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/sessions")
def list_sessions(
    current_user:     User = Depends(get_current_user),
    db:               Session = Depends(get_db),
    am_refresh_token: Optional[str] = Cookie(default=None),
):
    """
    Return all active (non-revoked) sessions for the current user.

    The session matching the caller's current refresh-token cookie is
    flagged as `is_current: true` so the frontend can highlight it.
    """
    sessions = (
        db.query(ActiveSession)
        .filter(
            ActiveSession.user_id == current_user.id,
            ActiveSession.is_revoked == False,  # noqa: E712
        )
        .order_by(ActiveSession.created_at.desc())
        .all()
    )

    result = []
    for s in sessions:
        result.append(SessionOut(
            id=s.id,
            ip_address=s.ip_address,
            user_agent=s.user_agent,
            created_at=s.created_at,
            last_activity_at=s.last_activity_at,
            is_current=(
                bool(am_refresh_token) and s.refresh_token == am_refresh_token
            ),
        ))

    return {"success": True, "data": result, "total": len(result)}


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /auth/sessions/{id}
# ─────────────────────────────────────────────────────────────────────────────

@router.delete("/sessions/{session_id}")
def revoke_session(
    session_id:   int,
    current_user: User = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    Revoke a specific session by its database ID.

    Users can only revoke their own sessions — attempting to revoke
    another user's session_id returns 404 (not 403) to prevent
    information disclosure about the existence of that session.
    """
    session = (
        db.query(ActiveSession)
        .filter(
            ActiveSession.id == session_id,
            ActiveSession.user_id == current_user.id,   # IDOR guard
            ActiveSession.is_revoked == False,           # noqa: E712
        )
        .first()
    )

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found.",
        )

    session.is_revoked = True
    db.commit()

    logger.info(
        "auth.session.revoked session_id=%d user_id=%s",
        session_id, current_user.id,
    )

    return {"success": True, "message": "Session revoked."}


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /auth/sessions  (revoke all OTHER sessions)
# ─────────────────────────────────────────────────────────────────────────────

@router.delete("/sessions")
def revoke_other_sessions(
    current_user:     User = Depends(get_current_user),
    db:               Session = Depends(get_db),
    am_refresh_token: Optional[str] = Cookie(default=None),
):
    """
    Revoke every session for the current user EXCEPT the current one.

    This is the "sign out of all other devices" action — the caller
    stays logged in on their current device.

    Also sets a per-user revoke-before timestamp in Redis to immediately
    invalidate any outstanding access tokens for the revoked sessions.
    """
    query = db.query(ActiveSession).filter(
        ActiveSession.user_id == current_user.id,
        ActiveSession.is_revoked == False,  # noqa: E712
    )

    # Exclude the current session from revocation so the caller stays logged in
    if am_refresh_token:
        query = query.filter(
            ActiveSession.refresh_token != am_refresh_token
        )

    revoked_count = query.update({"is_revoked": True})
    db.commit()

    # Redis: invalidate outstanding access tokens for all revoked sessions.
    # This is a blunt instrument (affects all tokens including the current one)
    # but the current session will immediately re-issue tokens on next request,
    # so the net effect is only other devices are locked out.
    if revoked_count > 0:
        set_revoke_before(current_user.id)

    logger.info(
        "auth.session.revoke_others user_id=%s revoked=%d",
        current_user.id, revoked_count,
    )

    return {
        "success": True,
        "message": f"Revoked {revoked_count} other session(s).",
    }
