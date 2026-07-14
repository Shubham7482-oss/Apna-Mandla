"""
app/models/udhar_transaction.py

Records each credit event on a UdharAccount.

Immutability: UdharTransactions are also append-only — corrections are
new UDHAR_ADJUSTMENT entries, never UPDATEs.

Link to main ledger:
  ledger_correlation_id — UUID shared with the LedgerEntry pair that
  recorded the corresponding cash movement. NULL for interest accruals
  (no immediate cash movement; cash moves only on repayment).
"""

import enum
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class UdharTxType(str, enum.Enum):
    UDHAR_DEBIT      = "UDHAR_DEBIT"       # Goods bought on credit
    UDHAR_REPAYMENT  = "UDHAR_REPAYMENT"   # Cash repayment made
    UDHAR_INTEREST   = "UDHAR_INTEREST"    # Periodic interest accrual
    UDHAR_ADJUSTMENT = "UDHAR_ADJUSTMENT"  # Admin correction (reversal)


class UdharTransaction(Base):
    __tablename__ = "udhar_transactions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    udhar_account_id: Mapped[int] = mapped_column(
        ForeignKey("udhar_accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )

    transaction_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    amount:           Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    # Outstanding balance on the account AFTER this transaction was applied
    outstanding_after: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    # Links to the WalletService/LedgerEntry correlation for cash flows
    ledger_correlation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    # Idempotency key — prevents double-processing the same event
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)

    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    udhar_account = relationship("UdharAccount", back_populates="transactions")
    order         = relationship("Order", foreign_keys=[order_id])

    __table_args__ = (
        CheckConstraint("amount > 0",             name="ck_udhar_txn_amount_pos"),
        CheckConstraint("outstanding_after >= 0", name="ck_udhar_txn_outstanding_nn"),
    )

    def __repr__(self) -> str:
        return (
            f"<UdharTransaction id={self.id} account={self.udhar_account_id} "
            f"{self.transaction_type} {self.amount} → {self.outstanding_after}>"
        )


# ORM-level immutability guard (same pattern as LedgerEntry)
@event.listens_for(UdharTransaction, "before_update")
def _block_udhar_txn_update(mapper, connection, target):
    raise RuntimeError(
        f"UdharTransaction id={target.id} is IMMUTABLE. Post a new UDHAR_ADJUSTMENT entry."
    )


@event.listens_for(UdharTransaction, "before_delete")
def _block_udhar_txn_delete(mapper, connection, target):
    raise RuntimeError(
        f"UdharTransaction id={target.id} cannot be deleted. Append-only ledger."
    )
