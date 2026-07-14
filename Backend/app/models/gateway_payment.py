"""
app/models/gateway_payment.py

Records external payment gateway interactions.

This is the SINGLE SOURCE OF TRUTH for gateway state.  The WalletService
is only called AFTER a GatewayPayment row confirms a successful charge.

Supported providers (hooks only — no real SDK calls):
  RAZORPAY | STRIPE | PHONEPE | PAYTM | MANUAL (admin top-up)
"""

import enum
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class GatewayProvider(str, enum.Enum):
    RAZORPAY = "RAZORPAY"
    STRIPE   = "STRIPE"
    PHONEPE  = "PHONEPE"
    PAYTM    = "PAYTM"
    MANUAL   = "MANUAL"   # Admin-initiated top-up


class GatewayPaymentStatus(str, enum.Enum):
    INITIATED  = "INITIATED"   # Order created at gateway
    AUTHORIZED = "AUTHORIZED"  # Gateway authorised; waiting capture
    CAPTURED   = "CAPTURED"    # Money debited; awaiting webhook confirmation
    SUCCESS    = "SUCCESS"     # Webhook confirmed; wallet credited
    FAILED     = "FAILED"      # Gateway declined
    REFUNDED   = "REFUNDED"    # Refund completed at gateway + wallet


class GatewayPayment(Base):
    __tablename__ = "gateway_payments"

    id:            Mapped[int]     = mapped_column(primary_key=True, index=True)

    # ── Who and why ───────────────────────────────────────────────────────────
    user_id:       Mapped[int]     = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    order_id:      Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True)

    # ── Amount ────────────────────────────────────────────────────────────────
    amount:        Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency:      Mapped[str]     = mapped_column(String(3),  nullable=False, default="INR")

    # ── Gateway fields ────────────────────────────────────────────────────────
    provider:      Mapped[str]     = mapped_column(String(20), nullable=False, index=True)
    status:        Mapped[str]     = mapped_column(String(20), nullable=False, default=GatewayPaymentStatus.INITIATED, index=True)

    # Gateway's own identifiers — used as idempotency keys into WalletService
    gateway_order_id:   Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    gateway_payment_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    gateway_signature:  Mapped[str | None] = mapped_column(String(256), nullable=True)  # HMAC from webhook

    # ── Failure ───────────────────────────────────────────────────────────────
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ── Raw webhook body (for debugging / dispute resolution) ─────────────────
    webhook_payload: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Ledger correlation (set after wallet credited) ────────────────────────
    ledger_correlation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at:    Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    completed_at:  Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refunded_at:   Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user  = relationship("User",  foreign_keys=[user_id])
    order = relationship("Order", foreign_keys=[order_id])

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_gw_payment_amount_pos"),
    )

    def __repr__(self) -> str:
        return (
            f"<GatewayPayment id={self.id} provider={self.provider} "
            f"status={self.status} amount={self.amount}>"
        )
