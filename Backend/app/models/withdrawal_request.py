"""
app/models/withdrawal_request.py

A withdrawal request represents a user's intent to move wallet balance
to their external bank account.

Lifecycle:
  PENDING → PROCESSING → COMPLETED
  PENDING → REJECTED

When PENDING:
  The withdrawal amount is immediately DEBITED from the wallet and
  a LedgerEntry (WITHDRAWAL, DR) is created. The money is held in
  the platform's escrow account until the admin approves.

When REJECTED:
  The amount is CREDITED back to the user's wallet (REFUND entry).

When COMPLETED:
  The admin has confirmed the bank transfer. No further ledger action.
"""

import enum
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey,
    Integer, Numeric, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class WithdrawalStatus(str, enum.Enum):
    PENDING    = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED  = "COMPLETED"
    REJECTED   = "REJECTED"


class WithdrawalRequest(Base, TimestampMixin):
    __tablename__ = "withdrawal_requests"

    id      = mapped_column(Integer, primary_key=True, index=True)
    user_id = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Use Numeric, never Float, for money
    amount  = mapped_column(Numeric(14, 2), nullable=False)
    status  = mapped_column(String(20), default=WithdrawalStatus.PENDING, nullable=False, index=True)

    # Prevents double-submission from the client
    idempotency_key = mapped_column(String(100), nullable=True, unique=True)

    # JSON snapshot of bank details at the time of request
    bank_details_snapshot = mapped_column(Text, nullable=True)

    # Admin fields
    admin_note         = mapped_column(String(500), nullable=True)
    processed_by_id    = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    processed_at       = mapped_column(DateTime(timezone=True), nullable=True)

    # Batch settlement
    settlement_batch_id = mapped_column(String(100), nullable=True, index=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    user         = relationship("User", foreign_keys=[user_id])
    processed_by = relationship("User", foreign_keys=[processed_by_id])

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_withdrawal_amount_positive"),
    )

    def __repr__(self) -> str:
        return f"<Withdrawal id={self.id} user_id={self.user_id} amount={self.amount} status={self.status}>"
