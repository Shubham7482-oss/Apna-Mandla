"""
app/services/admin_auth.py

Admin authentication helpers.

Admin tokens are signed with ADMIN_SECRET_KEY (separate from user SECRET_KEY)
and carry type="admin" so they cannot be used as user access tokens and
vice-versa.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from jose import jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import verify_password  # ← single source of truth
from app.models.admin import AdminUser

logger = logging.getLogger(__name__)


def create_admin_access_token(admin_id: str | int) -> str:
    """
    Issue a short-lived admin access token signed with ADMIN_SECRET_KEY.

    Claims:
        sub      — admin ID
        type     — "admin"  (prevents use as user token)
        jti      — unique token ID
        iss      — project name
        iat      — issued at (UTC, timezone-aware)
        exp      — expiry (UTC, timezone-aware)
    """
    now = datetime.now(timezone.utc)          # ← was datetime.utcnow() (deprecated)
    expire = now + timedelta(minutes=settings.ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": str(admin_id),
        "type": "admin",
        "jti": secrets.token_hex(16),
        "iss": settings.PROJECT_NAME,
        "iat": now,
        "exp": expire,
    }

    return jwt.encode(
        payload,
        settings.ADMIN_SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def authenticate_admin(
    db: Session,
    phone: str,
    password: str,
) -> AdminUser:
    """
    Verify admin credentials.  Returns the AdminUser on success.
    Raises HTTP 401 on any failure — intentionally indistinguishable
    between "wrong phone" and "wrong password" to prevent enumeration.
    """
    admin = (
        db.query(AdminUser)
        .filter(
            AdminUser.phone == phone,
            AdminUser.is_active == True,  # noqa: E712
        )
        .first()
    )

    # Deliberately run verify_password even on miss so timing is consistent.
    dummy_hash = "$2b$12$aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    stored_hash = admin.hashed_password if admin else dummy_hash

    password_ok = verify_password(password, stored_hash)

    if not admin or not password_ok:
        logger.warning(
            "Failed admin login attempt for phone=%s",
            phone[:4] + "***",   # partial mask — don't log full phone
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
        )

    logger.info("Admin authenticated: id=%s", admin.id)
    return admin
