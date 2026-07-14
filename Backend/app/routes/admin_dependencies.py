"""
app/routes/admin_dependencies.py

FastAPI dependency for admin panel authentication.

Admin tokens are signed with ADMIN_SECRET_KEY and carry type="admin".
This dependency enforces both claims so that:
  - A user access token cannot be used in admin endpoints.
  - An admin token cannot be used in user endpoints
    (user endpoints use get_current_user which enforces type="access").
"""

import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db          # ← single source; no duplicate
from app.models.admin import AdminUser

logger = logging.getLogger(__name__)

_bearer = HTTPBearer()


def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> AdminUser:
    """
    Validate an admin Bearer token and return the corresponding AdminUser.

    Checks (in order):
      1. JWT signature valid against ADMIN_SECRET_KEY.
      2. Token not expired.
      3. type claim == "admin".
      4. AdminUser exists and is active.
    """
    invalid_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired admin token.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            settings.ADMIN_SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
    except JWTError:
        raise invalid_exc

    if payload.get("type") != "admin":
        logger.warning("Non-admin token presented to admin endpoint.")
        raise invalid_exc

    admin_id = payload.get("sub")
    if not admin_id:
        raise invalid_exc

    try:
        admin_id_int = int(admin_id)
    except (ValueError, TypeError):
        raise invalid_exc

    admin = (
        db.query(AdminUser)
        .filter(
            AdminUser.id == admin_id_int,
            AdminUser.is_active == True,  # noqa: E712
        )
        .first()
    )

    if not admin:
        logger.warning("Admin token valid but admin_id=%s not found or inactive.", admin_id)
        raise invalid_exc

    return admin
