"""
app/models/fraud_flag.py

Records suspicious financial activity detected by FraudService.
Flags are informational — they do not automatically block transactions
but are reviewed by admin and can trigger wallet freezes.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class FraudFlagType(str, enum.Enum):
    RAPID_TRANSACTIONS     = "RAPID_TRANSACTIONS"     # Too many txns in short window
    LARGE_AMOUNT           = "LARGE_AMOUNT"           # Single txn exceeds threshold
    DAILY_LIMIT_EXCEEDED   = "DAILY_LIMIT_EXCEEDED"   # Daily cap hit
    VELOCITY_BREACH        = "VELOCITY_BREACH"        # Amount spike vs history
    IDEMPOTENCY_COLLISION  = "IDEMPOTENCY_COLLISION"  # Key reuse from different IP
    UNUSUAL_PATTERN        = "UNUSUAL_PATTERN"        # ML/heuristic catch-all


class FraudFlag(Base):
    __tablename__ = "fraud_flags"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    user_id:    Mapped[int]         = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    wallet_id:  Mapped[int | None]  = mapped_column(ForeignKey("wallets.id", ondelete="SET NULL"), nullable=True)

    flag_type:  Mapped[str]         = mapped_column(String(30), nullable=False, index=True)
    severity:   Mapped[str]         = mapped_column(String(10), nullable=False, default="MEDIUM")
    # LOW | MEDIUM | HIGH | CRITICAL

    amount:     Mapped[float | None]= mapped_column(Numeric(14, 2), nullable=True)
    description:Mapped[str]         = mapped_column(Text, nullable=False)

    # Resolved by admin
    is_resolved:Mapped[bool]        = mapped_column(Boolean, nullable=False, default=False, index=True)
    resolved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_note: Mapped[str | None]  = mapped_column(String(500), nullable=True)

    # Context
    ip_address: Mapped[str | None]  = mapped_column(String(45), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # ledger cid if applicable

    created_at: Mapped[datetime]    = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    user        = relationship("User", foreign_keys=[user_id])
    resolved_by = relationship("User", foreign_keys=[resolved_by_id])

    def __repr__(self) -> str:
        return (
            f"<FraudFlag id={self.id} user={self.user_id} "
            f"{self.flag_type} severity={self.severity} resolved={self.is_resolved}>"
        )
