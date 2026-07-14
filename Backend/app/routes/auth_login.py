from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import secrets
from pydantic import BaseModel
from typing import Dict, Any

from app.core.database import get_db
from app.models.user import User
from app.models.otp import OTP
from app.schemas.common import SuccessResponse
from app.core.config import settings
from app.core.otp_security import hash_otp
from app.services.sms_service import get_sms_provider
from app.services.audit_service import log_action

router = APIRouter(tags=["Authentication"])


class LoginRequest(BaseModel):
    phone_number: str


@router.post(
    "/login",
    response_model=SuccessResponse[Dict[str, Any]],
)
def login(
    data: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    client_ip = request.client.host if request.client else "unknown"

    try:
        # ==========================================================
        # 1️⃣ USER VALIDATION
        # ==========================================================
        user = (
            db.query(User)
            .filter(
                User.phone_number == data.phone_number,
                User.is_active == True,
                User.is_archived == False,
            )
            .first()
        )

        if not user:
            try:
                log_action(
                    db,
                    request,
                    action="LOGIN_FAILED",
                    description="User not found",
                )
            except Exception:
                pass

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found for this phone number",
            )

        # ==========================================================
        # 2️⃣ 60-SECOND COOLDOWN (PER IP)
        # ==========================================================
        last_otp = (
            db.query(OTP)
            .filter(
                OTP.ip_address == client_ip,
                OTP.purpose == "login",
            )
            .order_by(OTP.created_at.desc())
            .first()
        )

        if last_otp:
            time_elapsed = (now - last_otp.created_at).total_seconds()
            if time_elapsed < 60:
                try:
                    log_action(
                        db,
                        request,
                        action="OTP_RATE_LIMIT",
                        description="Cooldown violation",
                        user_id=user.id,
                    )
                except Exception:
                    pass

                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Please wait {int(60 - time_elapsed)} seconds before requesting again.",
                )

        # ==========================================================
        # 3️⃣ DAILY LIMIT (3 PER IP)
        # ==========================================================
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        daily_ip_otp_count = (
            db.query(OTP)
            .filter(
                OTP.created_at >= today_start,
                OTP.purpose == "login",
                OTP.ip_address == client_ip,
            )
            .count()
        )

        if daily_ip_otp_count >= 3:
            try:
                log_action(
                    db,
                    request,
                    action="OTP_DAILY_LIMIT",
                    description="Exceeded daily limit",
                    user_id=user.id,
                )
            except Exception:
                pass

            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Daily OTP limit reached (3 per IP). Try again tomorrow.",
            )

        # ==========================================================
        # 4️⃣ GENERATE & STORE HASHED OTP
        # ==========================================================
        otp_code = "".join(str(secrets.randbelow(10)) for _ in range(6))
        hashed_otp = hash_otp(otp_code)

        otp_entry = OTP(
            user_id=user.id,
            phone_number=user.phone_number,
            otp_hash=hashed_otp,
            purpose="login",
            expires_at=now + timedelta(minutes=5),
            is_used=False,
            ip_address=client_ip,
        )

        db.add(otp_entry)
        db.commit()

        # ==========================================================
        # 5️⃣ SEND SMS
        # ==========================================================
        sms_provider = get_sms_provider()
        sms_provider.send_sms(
            user.phone_number,
            f"Your Apna Mandla OTP is {otp_code}. It is valid for 5 minutes."
        )

        # ==========================================================
        # 6️⃣ AUDIT SUCCESS
        # ==========================================================
        try:
            log_action(
                db,
                request,
                action="OTP_SENT",
                description="Login OTP generated",
                user_id=user.id,
            )
        except Exception:
            pass

        # ==========================================================
        # 7️⃣ SAFE RESPONSE (NO None FIELD)
        # ==========================================================

        response_data = {
            "user_id": user.id,
            "otp_required": True,
            "resend_after": 60,
        }

        # Only include debug_otp if DEBUG = True
        if settings.DEBUG:
            response_data["debug_otp"] = otp_code

        return SuccessResponse(
            success=True,
            data=response_data,
            message="OTP sent successfully",
        )

    except HTTPException:
        raise

    except Exception:
        db.rollback()

        try:
            log_action(
                db,
                request,
                action="LOGIN_ERROR",
                description="Unexpected error during login",
            )
        except Exception:
            pass

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate login OTP. Please try again.",
        )