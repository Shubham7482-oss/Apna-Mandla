# app/services/otp_service.py

from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.core.security import generate_otp, hash_otp, verify_otp
from app.core.config import settings


class OTPService:
    """
    OTP handling service.

    Handles:
    - generation
    - hashing
    - expiry check
    - attempt limits (logic placeholder)

    NOTE:
    - Actual persistence will be implemented
      via verification tables later.
    """

    @staticmethod
    def generate():
        otp = generate_otp()
        return {
            "otp": otp,
            "otp_hash": hash_otp(otp),
            "expires_at": datetime.utcnow()
            + timedelta(seconds=settings.OTP_EXPIRY_SECONDS),
        }

    @staticmethod
    def verify(
        plain_otp: str,
        stored_hash: str,
        expires_at: datetime,
    ) -> bool:
        if datetime.utcnow() > expires_at:
            return False
        return verify_otp(plain_otp, stored_hash)
