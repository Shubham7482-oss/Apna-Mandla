"""
app/routes/auth_forgot.py

Forgot-password flow.

1. Client submits a phone number.
2. If the number exists, an OTP is generated and sent via SMS.
3. The response is always the same message — it does not reveal whether
   the phone number is registered (prevents user enumeration).
4. The OTP is verified in /auth/reset-password (auth_password.py).
"""

import logging
import secrets

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.otp_security import hash_otp
from app.models.otp import OTP
from app.models.user import User
from app.services.sms_service import get_sms_provider

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Authentication"])

_SAFE_RESPONSE = {
    "status": "success",
    "message": "If that phone number is registered, an OTP has been sent.",
}


class ForgotPasswordRequest(BaseModel):
    phone_number: str


@router.post("/forgot-password")
def forgot_password(
    data: ForgotPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Trigger a password-reset OTP.

    Rate limits (per client IP, per purpose):
      - 60-second cooldown between requests.
      - 3 requests per calendar day.

    Always returns the same body regardless of whether the number exists.
    """
    now = datetime.now(timezone.utc)
    client_ip = request.client.host if request.client else "unknown"

    try:
        user = (
            db.query(User)
            .filter(
                User.phone_number == data.phone_number,
                User.is_archived == False,  # noqa: E712
            )
            .first()
        )

        # Return the same response whether user exists or not.
        # Do all rate-limit checks before the user-existence guard so
        # the timing is consistent and doesn't leak user existence.
        last_otp = (
            db.query(OTP)
            .filter(
                OTP.ip_address == client_ip,
                OTP.purpose == "password-reset",
            )
            .order_by(OTP.created_at.desc())
            .first()
        )

        if last_otp and (now - last_otp.created_at).total_seconds() < 60:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Please wait 60 seconds before requesting a new OTP.",
            )

        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        daily_count = (
            db.query(OTP)
            .filter(
                OTP.created_at >= today_start,
                OTP.purpose == "password-reset",
                OTP.ip_address == client_ip,
            )
            .count()
        )
        if daily_count >= 3:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Daily password reset limit reached for your IP.",
            )

        if not user:
            # Still insert a dummy rate-limit record so timing is identical
            # and the rate-limit check above fires on the next request.
            # Use a phantom user_id=0 placeholder.
            otp_entry = OTP(
                user_id=0,
                phone_number=data.phone_number,
                otp_hash="",
                purpose="password-reset",
                expires_at=now + timedelta(minutes=10),
                ip_address=client_ip,
                is_used=True,  # immediately invalidated
            )
            db.add(otp_entry)
            db.commit()
            return _SAFE_RESPONSE

        # ── Generate OTP with secrets (not random) ────────────────────────────
        otp_code = "".join(str(secrets.randbelow(10)) for _ in range(6))
        hashed = hash_otp(otp_code)

        otp_entry = OTP(
            user_id=user.id,
            phone_number=user.phone_number,
            otp_hash=hashed,
            purpose="password-reset",
            expires_at=now + timedelta(minutes=10),
            ip_address=client_ip,
            is_used=False,
        )
        db.add(otp_entry)
        db.commit()

        sms_provider = get_sms_provider()
        sms_provider.send_sms(
            user.phone_number,
            f"Your Apna Mandla password reset OTP is {otp_code}. "
            "Valid for 10 minutes. Do not share it with anyone.",
        )

        logger.info(
            "Password reset OTP issued for user_id=%s from IP=%s",
            user.id,
            client_ip,
        )

        return _SAFE_RESPONSE

    except HTTPException:
        raise
    except Exception:
        db.rollback()
        logger.exception("Error in forgot_password for IP=%s", client_ip)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again later.",
        )
