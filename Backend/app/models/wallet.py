"""
app/models/wallet.py

Wallet — one per user (customers, sellers, riders, platform).

Design rules:
  - `balance` is a CACHED value, always updated atomically alongside
    a new LedgerEntry in the same DB transaction. Never update balance
    alone without a corresponding ledger entry.
  - `WalletTransaction` is kept for backward-compatibility only. All new
    code must write to `LedgerEntry` exclusively via WalletService.
  - Balance integrity can be verified at any time by summing all
    ledger entries: SUM(CREDIT) - SUM(DEBIT) == balance.
"""

import enum
from decimal import Decimal

from sqlalchemy import (
    Boolean, CheckConstraint, Column, ForeignKey,
    Integer, Numeric, String, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


# ─────────────────────────────────────────────────────────────────────────────
# WALLET
# ─────────────────────────────────────────────────────────────────────────────

class Wallet(Base, TimestampMixin):
    """One wallet per user. Balance is always kept in sync with LedgerEntries."""

    __tablename__ = "wallets"

    id       = Column(Integer, primary_key=True, index=True)
    user_id  = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    # Cached running balance — ALWAYS updated atomically with LedgerEntry.
    # Source of truth is the ledger; this is a performance optimisation.
    balance  = Column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    is_frozen = Column(Boolean, default=False, nullable=False)

    # ── Relationships ─────────────────────────────────────────────────────────
    user = relationship("User", back_populates="wallet")

    # Primary ledger (double-entry)
    ledger_entries = relationship(
        "LedgerEntry",
        back_populates="wallet",
        cascade="all, delete-orphan",
        order_by="LedgerEntry.id",
    )

    # Legacy transaction table — kept for existing data, no longer written to
    transactions = relationship(
        "WalletTransaction",
        back_populates="wallet",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint("balance >= 0", name="ck_wallet_balance_non_negative"),
    )

    def __repr__(self) -> str:
        return f"<Wallet id={self.id} user_id={self.user_id} balance={self.balance}>"


# ─────────────────────────────────────────────────────────────────────────────
# WALLET TRANSACTION (LEGACY — do not write new entries here)
# ─────────────────────────────────────────────────────────────────────────────

class TransactionType(str, enum.Enum):
    CREDIT = "CREDIT"
    DEBIT  = "DEBIT"


class WalletTransaction(Base, TimestampMixin):
    """
    Legacy transaction log. Kept so existing data is not orphaned.
    New code uses LedgerEntry exclusively.
    """
    __tablename__ = "wallet_transactions"

    id               = Column(Integer, primary_key=True, index=True)
    wallet_id        = Column(Integer, ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False, index=True)
    transaction_type = Column(String(10), nullable=False, index=True)
    amount           = Column(Numeric(14, 2), nullable=False)
    order_id         = Column(Integer, ForeignKey("orders.id",            ondelete="SET NULL"), nullable=True, index=True)
    udhar_transaction_id = Column(Integer, ForeignKey("udhar_transactions.id", ondelete="SET NULL"), nullable=True, index=True)

    wallet           = relationship("Wallet",          back_populates="transactions")
    order            = relationship("Order")
    udhar_transaction = relationship("UdharTransaction")
