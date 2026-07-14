# backend/app/services/otp_throttle.py

import time
from collections import defaultdict
from datetime import datetime

# Structure:
# {
#   "ip": {
#       "count": 0,
#       "last_sent": timestamp,
#       "date": "YYYY-MM-DD"
#   }
# }

otp_tracker = defaultdict(dict)

OTP_COOLDOWN_SECONDS = 60
OTP_DAILY_LIMIT = 3


def validate_otp_request(client_ip: str):
    now = time.time()
    today = datetime.utcnow().date().isoformat()

    record = otp_tracker.get(client_ip)

    # First request ever
    if not record:
        otp_tracker[client_ip] = {
            "count": 1,
            "last_sent": now,
            "date": today,
        }
        return

    # Reset daily count if date changed
    if record["date"] != today:
        otp_tracker[client_ip] = {
            "count": 1,
            "last_sent": now,
            "date": today,
        }
        return

    # Check daily limit
    if record["count"] >= OTP_DAILY_LIMIT:
        raise Exception("Daily OTP limit exceeded. Try again tomorrow.")

    # Check cooldown
    if now - record["last_sent"] < OTP_COOLDOWN_SECONDS:
        raise Exception("Please wait 60 seconds before requesting OTP again.")

    # Update record
    record["count"] += 1
    record["last_sent"] = now