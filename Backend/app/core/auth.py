"""
app/core/auth.py

get_current_user() FastAPI dependency.

Token URL updated to /auth/login (was /auth/auth/login — the old double-prefix).
"""

from typing import List, Union

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.core.token_store import is_access_token_revoked
from app.models.admin import AdminUser
from app.models.user import User

# tokenUrl is a documentation hint for Swagger UI; update it to the clean URL.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Validate the Bearer access token and return the authenticated User.

    Order (cheapest first):
      1. JWT decode + type == "access"   (CPU only)
      2. JTI deny-list / revoke-before   (Redis ~0.2ms)
      3. User DB lookup                  (one indexed read)
    """
    payload = decode_access_token(token)
    if not payload:
        raise _CREDENTIALS_EXCEPTION

    user_id_str: str | None = payload.get("sub")
    if not user_id_str:
        raise _CREDENTIALS_EXCEPTION

    if is_access_token_revoked(payload):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        uid = int(user_id_str)
    except (ValueError, TypeError):
        raise _CREDENTIALS_EXCEPTION

    user = db.query(User).filter(User.id == uid).first()
    if user is None:
        raise _CREDENTIALS_EXCEPTION

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def require_roles(required_roles: List[str]):
    """Backward-compat role guard. Prefer app.core.rbac for new code."""
    def role_checker(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> Union[User, AdminUser]:
        if current_user.user_type not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        if current_user.user_type == "admin":
            admin = (
                db.query(AdminUser).filter(AdminUser.user_id == current_user.id).first()
            )
            if not admin:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Admin profile not found.",
                )
            return admin
        return current_user
    return role_checker
