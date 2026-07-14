# backend/app/services/redis_throttle.py

from fastapi import HTTPException, status
from app.core.redis_client import redis_client
from datetime import datetime

OTP_DAILY_LIMIT = 3
OTP_COOLDOWN_SECONDS = 60


def check_otp_limits(ip_address: str):

    today_key = f"otp:daily:{ip_address}:{datetime.utcnow().date()}"
    cooldown_key = f"otp:cooldown:{ip_address}"

    # Cooldown check
    if redis_client.exists(cooldown_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Please wait before requesting OTP again.",
        )

    # Daily count
    daily_count = redis_client.get(today_key)
    daily_count = int(daily_count) if daily_count else 0

    if daily_count >= OTP_DAILY_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Daily OTP limit reached. Try again tomorrow.",
        )

    # Increment daily counter
    pipe = redis_client.pipeline()
    pipe.incr(today_key)
    pipe.expire(today_key, 86400)  # 24 hours
    pipe.setex(cooldown_key, OTP_COOLDOWN_SECONDS, "1")
    pipe.execute()