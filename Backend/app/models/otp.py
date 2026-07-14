from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from datetime import datetime, timezone
from app.models.base import Base


class OTP(Base):
    __tablename__ = "otps"

    # ───────────────────────────────
    # PRIMARY KEY
    # ───────────────────────────────
    id = Column(Integer, primary_key=True, index=True)

    # ───────────────────────────────
    # IDENTITY
    # ───────────────────────────────
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )

    phone_number = Column(String(25), index=True, nullable=True)

    # 🔥 SECURITY: IP tracking for rate limiting (IPv4 + IPv6 safe)
    ip_address = Column(String(45), index=True, nullable=True)

    # ───────────────────────────────
    # OTP DATA
    # ───────────────────────────────
    otp_hash = Column(String, nullable=False)

    # Purpose: signup, login, reset_password, change_phone
    purpose = Column(String(50), default="signup", index=True)

    # ───────────────────────────────
    # SECURITY & EXPIRY
    # ───────────────────────────────
    expires_at = Column(DateTime(timezone=True), nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    is_used = Column(Boolean, default=False)
    attempt_count = Column(Integer, default=0)
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)

    # ───────────────────────────────
    # HELPERS
    # ───────────────────────────────
    @property
    def is_expired(self) -> bool:
        """
        Returns True if OTP is expired.
        Timezone-safe comparison.
        """
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def can_attempt(self) -> bool:
        """
        Prevent brute force.
        Max 5 attempts.
        """
        return self.attempt_count < 5 and not self.is_used