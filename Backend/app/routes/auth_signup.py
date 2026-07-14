from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import secrets

from app.core.database import get_db
from app.models.user import User
from app.models.otp import OTP
from app.schemas.user import UserBase
from app.core.otp_security import hash_otp # Import the hash function
from app.services.sms_service import get_sms_provider

router = APIRouter(tags=["Authentication"])


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(data: UserBase, request: Request, db: Session = Depends(get_db)):
    """
    Secure Signup Flow:
    1. Check for existing user.
    2. Enforce rate limiting.
    3. Create a new User (inactive until verified).
    4. Generate and HASH a 6-digit OTP.
    5. Send the raw OTP via SMS.
    """
    now = datetime.now(timezone.utc)
    client_ip = request.client.host if request.client else "unknown"

    # 1. Check if user already exists
    existing_user = (
        db.query(User).filter(User.phone_number == data.phone_number).first()
    )
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This phone number is already registered. Please login.",
        )

    # 2. Rate Limiting (e.g., max 5 signups per IP per day)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    daily_ip_signup_count = (
        db.query(User)
        .filter(User.created_at >= today_start, User.signup_ip == client_ip)
        .count()
    )
    if daily_ip_signup_count >= 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Maximum signup attempts reached for today from this IP.",
        )

    try:
        # 3. Create User (initially inactive)
        new_user = User(
            phone_number=data.phone_number,
            email=data.email,
            name=data.name,
            user_type="CUSTOMER",
            phone_verified=False,
            is_active=False,  # Start as inactive
            signup_ip=client_ip,
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        # 4. Generate and Hash OTP
        otp_code = "".join(str(secrets.randbelow(10)) for _ in range(6))
        hashed_otp = hash_otp(otp_code) # Hash the OTP

        new_otp = OTP(
            user_id=new_user.id,
            phone_number=data.phone_number,
            otp_hash=hashed_otp, # Store the hash
            purpose="signup",
            expires_at=now + timedelta(minutes=10),
            ip_address=client_ip,
        )
        db.add(new_otp)
        db.commit()

        # 5. Send OTP via SMS
        sms_provider = get_sms_provider()
        sms_provider.send_sms(
            data.phone_number,
            f"Your verification OTP is {otp_code}. It is valid for 10 minutes.",
        )

        return {
            "message": "Registration successful. OTP sent for verification.",
            "user_id": new_user.id,
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        print(f"Error in signup: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user. Please try again later.",
        )


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(data: UserBase, request: Request, db: Session = Depends(get_db)):
    # Alias for signup
    return signup(data, request, db)
