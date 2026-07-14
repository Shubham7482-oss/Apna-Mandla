"""
app/routes/auth_verify.py

OTP verification — login and signup flows.

On success:
  - Issues access token (in JSON body — used as Authorization: Bearer).
  - Issues refresh token as HttpOnly cookie (hidden from JS).
  - Sets a CSRF token as a readable cookie (for the /refresh endpoint).

API contract (success):
  HTTP 200
  Set-Cookie: am_refresh_token=<jwt>; HttpOnly; Secure; SameSite=Strict
  Set-Cookie: am_csrf_token=<random>;  Secure; SameSite=Strict
  {
    "success": true,
    "data": {
      "access_token": "<jwt>",
      "token_type":   "bearer",
      "user_id":       123,
      "user_type":    "CUSTOMER",
      "name":         "John Doe"
    }
  }
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.csrf import generate_csrf_token, set_csrf_cookie
from app.core.database import get_db
from app.core.otp_security import verify_otp_hash
from app.core.rate_limiter import otp_verify_limiter
from app.core.security import create_token_pair
from app.models.active_session import ActiveSession
from app.models.otp import OTP
from app.models.user import User
from app.schemas.common import SuccessResponse

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Authentication"])


class OTPVerifyRequest(BaseModel):
    phone_number: str
    otp: str
    purpose: str  # "login" or "signup"


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


@router.post("/verify-otp", response_model=SuccessResponse[Dict[str, Any]])
def verify_otp(
    data: OTPVerifyRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    _: None = Depends(otp_verify_limiter),
):
    now = datetime.now(timezone.utc)
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("User-Agent", "")

    if data.purpose not in ("login", "signup"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid OTP purpose.")

    # ── Fetch and validate OTP ────────────────────────────────────────────────
    otp_record = (
        db.query(OTP)
        .filter(
            OTP.phone_number == data.phone_number,
            OTP.purpose == data.purpose,
            OTP.is_used == False,
            OTP.expires_at > now,
        )
        .order_by(OTP.created_at.desc())
        .first()
    )

    if (otp_record and (otp_record.attempt_count or 0) >= 5):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many invalid attempts.")

    if not otp_record or not verify_otp_hash(data.otp, otp_record.otp_hash):
        if otp_record:
            otp_record.attempt_count = (otp_record.attempt_count or 0) + 1
            db.commit()
        logger.warning(
            "otp.verify.failed phone=%s purpose=%s ip=%s",
            data.phone_number[-4:],  # last 4 digits only — no full PII in logs
            data.purpose,
            client_ip,
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired OTP.")

    otp_record.is_used = True

    # ── User lookup ───────────────────────────────────────────────────────────
    user = db.query(User).filter(User.phone_number == data.phone_number).first()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")

    if data.purpose == "login" and not user.is_active:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Account is inactive. Please verify your phone number first.",
        )

    if data.purpose == "signup":
        user.is_active = True
        user.phone_verified = True

    # ── Issue token pair ──────────────────────────────────────────────────────
    tokens = create_token_pair(subject=str(user.id))

    new_session = ActiveSession(
        user_id=user.id,
        refresh_token=tokens.refresh_token,
        ip_address=client_ip,
        user_agent=user_agent[:512],
    )
    db.add(new_session)
    db.commit()

    # ── Set cookies ───────────────────────────────────────────────────────────
    _set_refresh_cookie(response, tokens.refresh_token)
    csrf_token = generate_csrf_token()
    set_csrf_cookie(response, csrf_token)

    logger.info(
        "auth.otp.verified purpose=%s user_id=%s ip=%s",
        data.purpose, user.id, client_ip,
    )

    return SuccessResponse(
        success=True,
        data={
            "access_token": tokens.access_token,
            "token_type":   tokens.token_type,
            "user_id":      user.id,
            "user_type":    user.user_type,
            "name":         user.name,
        },
        message=f"OTP for {data.purpose} verified successfully.",
    )
