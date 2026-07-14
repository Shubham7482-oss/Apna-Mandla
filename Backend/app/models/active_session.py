"""
app/models/active_session.py

Tracks every live refresh-token session.

Added in this revision:
  - ip_address   — client IP at login time (IPv6-safe, 45 chars)
  - user_agent   — browser/app User-Agent string (512 chars)
  - device_info  — optional structured JSON (platform, app version, etc.)

These fields are nullable so existing rows are not affected.
See alembic/versions/002_add_session_fields.py for the migration.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Boolean, Text
from sqlalchemy.orm import relationship

from app.models.base import Base


class ActiveSession(Base):
    __tablename__ = "active_sessions"

    id = Column(Integer, primary_key=True, index=True)

    # ── Ownership ─────────────────────────────────────────────────────────────
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Token ─────────────────────────────────────────────────────────────────
    # Full JWT string stored so we can look up and revoke by value.
    # Increased to 1024 to accommodate longer JWTs.
    refresh_token = Column(String(1024), nullable=False, index=True)

    # ── Status ────────────────────────────────────────────────────────────────
    is_revoked = Column(Boolean, default=False, nullable=False)

    # ── Device / origin metadata ──────────────────────────────────────────────
    ip_address = Column(String(45), nullable=True)    # IPv4 (15) or IPv6 (45)
    user_agent = Column(String(512), nullable=True)   # browser / app UA string
    device_info = Column(Text, nullable=True)         # optional JSON payload

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    last_activity_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user = relationship("User", back_populates="sessions")
