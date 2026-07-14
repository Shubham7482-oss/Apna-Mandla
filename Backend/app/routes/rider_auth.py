from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    generate_otp,
    hash_otp,
    verify_otp,
)
from app.models.user import User
from app.models.rider_profile import RiderProfile

router = APIRouter(prefix="/rider/auth", tags=["Rider Authentication"])


# ───────────────────────────────
# RIDER SIGNUP (BASE + PROFILE)
# ───────────────────────────────
@router.post("/signup", status_code=status.HTTP_201_CREATED)
def rider_signup(
    phone_number: str,
    email: str,
    full_name: str,
    db: Session = Depends(get_db),
):
    existing_user = (
        db.query(User)
        .filter((User.phone_number == phone_number) | (User.email == email))
        .first()
    )
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with phone or email already exists",
        )

    user = User(
        phone_number=phone_number,
        email=email,
        user_type="rider",
        phone_verified=False,
        email_verified=False,
        is_active=True,
        is_archived=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    rider_profile = RiderProfile(
        user_id=user.id,
        full_name=full_name,
        phone_verified=False,
        email_verified=False,
        aadhaar_verified=False,
        is_active_worker=False,
        available_for_work=False,
        suspended=False,
    )

    db.add(rider_profile)
    db.commit()
    db.refresh(rider_profile)

    return {
        "message": "Rider created. Phone/Aadhaar verification and admin approval pending.",
        "user_id": user.id,
        "rider_profile_id": rider_profile.id,
    }


# ───────────────────────────────
# SEND OTP (DEV / MOCK)
# ───────────────────────────────
@router.post("/send-otp")
def send_otp(
    user_id: int,
    purpose: str,  # PHONE / AADHAAR
    db: Session = Depends(get_db),
):
    user = (
        db.query(User)
        .filter(
            User.id == user_id,
            User.user_type == "rider",
            User.is_archived == False,
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rider not found",
        )

    if purpose not in ("PHONE", "AADHAAR"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP purpose",
        )

    otp = generate_otp()
    otp_hash = hash_otp(otp)

    # NOTE:
    # OTP persistence, expiry & retry limits
    # intentionally skipped (DEV MODE)

    return {
        "message": "OTP generated (mock)",
        "otp": otp,          # ⚠️ REMOVE IN PROD
        "otp_hash": otp_hash,
        "purpose": purpose,
    }


# ───────────────────────────────
# VERIFY OTP
# ───────────────────────────────
@router.post("/verify-otp")
def verify_otp_route(
    user_id: int,
    plain_otp: str,
    otp_hash: str,
    purpose: str,
    db: Session = Depends(get_db),
):
    user = (
        db.query(User)
        .filter(
            User.id == user_id,
            User.user_type == "rider",
            User.is_archived == False,
        )
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rider not found",
        )

    if purpose not in ("PHONE", "AADHAAR"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP purpose",
        )

    if not verify_otp(plain_otp, otp_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP",
        )

    rider_profile = (
        db.query(RiderProfile)
        .filter(RiderProfile.user_id == user.id)
        .first()
    )

    if not rider_profile:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Rider profile missing",
        )

    if purpose == "PHONE":
        user.phone_verified = True
        rider_profile.phone_verified = True

    if purpose == "AADHAAR":
        rider_profile.aadhaar_verified = True

    db.commit()

    return {
        "message": "OTP verified successfully",
        "purpose": purpose,
    }