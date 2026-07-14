"""
app/routes/auth_otp.py

Legacy login-OTP verification path. Kept for client backward compatibility.
New clients should use POST /auth/verify-otp with purpose="login".

Same cookie / CSRF behaviour as auth_verify.py.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.csrf import generate_csrf_token, set_csrf_cookie
from app.core.database import get_db
from app.core.otp_security import verify_otp_hash
from app.core.rate_limiter import otp_verify_limiter
from app.core.security import create_token_pair
from app.models.active_session import ActiveSession
from app.models.otp import OTP
from app.models.user import User
from app.schemas.common import SuccessResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Authentication"])


class VerifyLoginOTPRequest(BaseModel):
    phone_number: str
    otp: str


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


@router.post("/verify-login-otp", response_model=SuccessResponse[Dict[str, Any]])
def verify_login_otp(
    data: VerifyLoginOTPRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    _: None = Depends(otp_verify_limiter),
):
    now = datetime.now(timezone.utc)
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("User-Agent", "")

    user = db.query(User).filter(User.phone_number == data.phone_number).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    otp_entry = (
        db.query(OTP)
        .filter(
            OTP.user_id == user.id,
            OTP.purpose == "login",
            OTP.is_used == False,
            OTP.expires_at > now,
        )
        .order_by(OTP.created_at.desc())
        .first()
    )

    if not otp_entry:
        raise HTTPException(status_code=404, detail="No valid OTP found. Please request a new one.")

    if (otp_entry.attempt_count or 0) >= 5:
        raise HTTPException(status_code=429, detail="Too many invalid attempts. Request a new OTP.")

    if not verify_otp_hash(data.otp, otp_entry.otp_hash):
        otp_entry.attempt_count = (otp_entry.attempt_count or 0) + 1
        db.commit()
        remaining = 5 - otp_entry.attempt_count
        logger.warning(
            "auth.otp.invalid user_id=%s remaining_attempts=%d ip=%s",
            user.id, remaining, client_ip,
        )
        raise HTTPException(
            status_code=400,
            detail=f"Invalid OTP. {remaining} attempt(s) remaining.",
        )

    otp_entry.is_used = True

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive.")

    if not user.phone_verified:
        user.phone_verified = True

    tokens = create_token_pair(subject=str(user.id))

    try:
        db.add(ActiveSession(
            user_id=user.id,
            refresh_token=tokens.refresh_token,
            ip_address=client_ip,
            user_agent=user_agent[:512],
            is_revoked=False,
        ))
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not create session.")

    _set_refresh_cookie(response, tokens.refresh_token)
    csrf_token = generate_csrf_token()
    set_csrf_cookie(response, csrf_token)

    logger.info("auth.login.success user_id=%s ip=%s", user.id, client_ip)

    return SuccessResponse(
        success=True,
        data={
            "access_token": tokens.access_token,
            "token_type":   tokens.token_type,
            "user_id":      user.id,
            "user_type":    user.user_type,
            "name":         user.name,
        },
        message="Login successful",
    )
