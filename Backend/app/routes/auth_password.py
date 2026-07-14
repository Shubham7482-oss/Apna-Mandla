from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, timezone

from app.core.database import get_db
from app.core.security import get_password_hash
from app.models.user import User
from app.core.auth import get_current_user
from app.core.otp_security import verify_otp_hash
from app.models.otp import OTP

router = APIRouter(tags=["Authentication"])


class SetPasswordRequest(BaseModel):
    new_password: str


@router.post("/set-password")
def set_password(
    data: SetPasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Allows an authenticated user to set or change their own password.
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )

    current_user.password_hash = get_password_hash(data.new_password)
    db.commit()
    return {"message": "Password set successfully"}


class ResetPasswordRequest(BaseModel):
    phone_number: str
    otp: str
    new_password: str


@router.post("/reset-password")
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    """
    Password reset via phone number, protected by OTP verification.
    """
    # Find a valid, un-used OTP for password reset
    otp_record = (
        db.query(OTP)
        .filter(
            OTP.phone_number == data.phone_number,
            OTP.purpose == "password-reset",  # Specific purpose
            OTP.is_used == False,
            OTP.expires_at > datetime.now(timezone.utc),
        )
        .order_by(OTP.created_at.desc())
        .first()
    )

    if not otp_record or not verify_otp_hash(data.otp, otp_record.otp_hash):
        if otp_record:
            otp_record.attempt_count += 1
            db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired OTP"
        )

    # Mark OTP as used
    otp_record.is_used = True

    # Find the user associated with the phone number
    user = (
        db.query(User)
        .filter(User.phone_number == data.phone_number, User.is_archived == False)
        .first()
    )
    if not user:
        # This should ideally not happen if OTP was issued correctly
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    # Set new password
    user.password_hash = get_password_hash(data.new_password)
    db.commit()

    return {"message": "Password reset successfully"}
