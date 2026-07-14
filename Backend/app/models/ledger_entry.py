"""
app/models/ledger_entry.py

Immutable double-entry ledger.

Immutability is enforced at THREE layers:
  1. ORM layer    — SQLAlchemy before_update / before_delete events raise
                    immediately inside the same process.
  2. Service layer — WalletService never calls session.merge() or update().
  3. DB layer     — Migration 004 adds a DB trigger (PostgreSQL) or a
                    strict CHECK that always fails on UPDATE (SQLite fallback).

Columns added in this revision:
  session_id      — links the entry to the ActiveSession that triggered it
  udhar_account_id — non-null only for udhar-sourced movements
"""

import enum
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256

from sqlalchemy import (
    BigInteger, CheckConstraint, DateTime, ForeignKey,
    Numeric, String, UniqueConstraint, event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


# ─────────────────────────────────────────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────────────────────────────────────────

class EntrySide(str, enum.Enum):
    DR = "DR"   # Debit  — money / obligation leaves this wallet
    CR = "CR"   # Credit — money / obligation enters this wallet


class TransactionPurpose(str, enum.Enum):
    """Business purpose (WHY the money moved)."""
    TOPUP            = "TOPUP"
    ORDER_PAYMENT    = "ORDER_PAYMENT"
    REFUND           = "REFUND"
    COMMISSION       = "COMMISSION"
    WITHDRAWAL       = "WITHDRAWAL"
    DELIVERY_FEE     = "DELIVERY_FEE"
    COD_SETTLEMENT   = "COD_SETTLEMENT"
    ADJUSTMENT       = "ADJUSTMENT"
    # ── Udhar (credit system) ─────────────────────────────────────────────────
    UDHAR_DEBIT      = "UDHAR_DEBIT"      # shop credits goods on udhar
    UDHAR_REPAYMENT  = "UDHAR_REPAYMENT"  # customer repays cash → shop
    UDHAR_INTEREST   = "UDHAR_INTEREST"   # interest accrued on outstanding
    UDHAR_ADJUSTMENT = "UDHAR_ADJUSTMENT" # admin correction on udhar account


# ─────────────────────────────────────────────────────────────────────────────
# MODEL
# ─────────────────────────────────────────────────────────────────────────────

class LedgerEntry(Base):
    """
    Immutable, hash-chained, double-entry ledger record.
    One row per accounting side per business event.

    RULES — enforced in code AND database:
      • NEVER UPDATE a row. Every correction is a new reversal entry.
      • NEVER DELETE a row.
      • Every business event creates exactly two rows (DR + CR) with
        the same correlation_id.
    """
    __tablename__ = "ledger_entries"

    # ── Identity ──────────────────────────────────────────────────────────────
    id:              Mapped[int] = mapped_column(primary_key=True, index=True)
    sequence_number: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, index=True)

    # ── Tamper-evidence ───────────────────────────────────────────────────────
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_hash:    Mapped[str] = mapped_column(String(64), nullable=False)

    # ── Wallet ────────────────────────────────────────────────────────────────
    wallet_id: Mapped[int] = mapped_column(
        ForeignKey("wallets.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # ── Double-entry ──────────────────────────────────────────────────────────
    entry_side:       Mapped[str] = mapped_column(String(2),  nullable=False, index=True)
    transaction_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    correlation_id:   Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    # ── Amounts ───────────────────────────────────────────────────────────────
    amount:        Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    # ── Optional references ───────────────────────────────────────────────────
    order_id:         Mapped[int | None] = mapped_column(ForeignKey("orders.id",              ondelete="SET NULL"), nullable=True, index=True)
    withdrawal_id:    Mapped[int | None] = mapped_column(ForeignKey("withdrawal_requests.id", ondelete="SET NULL"), nullable=True, index=True)
    udhar_account_id: Mapped[int | None] = mapped_column(ForeignKey("udhar_accounts.id",      ondelete="SET NULL"), nullable=True, index=True)

    # ── Audit / session linkage ───────────────────────────────────────────────
    # Links this ledger entry to the web session that triggered it.
    session_id:       Mapped[int | None] = mapped_column(ForeignKey("active_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    description:      Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Idempotency ───────────────────────────────────────────────────────────
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ── Timestamp ─────────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    wallet        = relationship("Wallet",          back_populates="ledger_entries")
    order         = relationship("Order",           foreign_keys=[order_id])
    withdrawal    = relationship("WithdrawalRequest", foreign_keys=[withdrawal_id])
    udhar_account = relationship("UdharAccount",    foreign_keys=[udhar_account_id])
    session       = relationship("ActiveSession",   foreign_keys=[session_id])

    # ── DB constraints ────────────────────────────────────────────────────────
    __table_args__ = (
        CheckConstraint("entry_side IN ('DR', 'CR')",    name="ck_ledger_entry_side_valid"),
        CheckConstraint("amount > 0",                    name="ck_ledger_amount_positive"),
        UniqueConstraint("wallet_id", "idempotency_key", name="uq_ledger_idempotency"),
    )

    def __repr__(self) -> str:
        return (
            f"<LedgerEntry seq={self.sequence_number} "
            f"wallet={self.wallet_id} {self.entry_side} "
            f"{self.transaction_type} {self.amount} → {self.balance_after}>"
        )

    # ── Hash helper ───────────────────────────────────────────────────────────

    @staticmethod
    def compute_hash(
        wallet_id: int,
        entry_side: str,
        amount: Decimal,
        balance_after: Decimal,
        prev_hash: str,
        timestamp: str,
        correlation_id: str,
    ) -> str:
        raw = (
            f"{wallet_id}|{entry_side}|{amount}|"
            f"{balance_after}|{prev_hash}|{timestamp}|{correlation_id}"
        )
        return sha256(raw.encode("utf-8")).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# ORM-LEVEL IMMUTABILITY GUARDS
#
# These fire synchronously within the same SQLAlchemy session, BEFORE the SQL
# is sent to the database.  They catch accidental updates/deletes in Python
# code before a DB round-trip is even attempted.
#
# The DB-level trigger (migration 004) provides a second line of defence
# for direct SQL access, psql console edits, etc.
# ─────────────────────────────────────────────────────────────────────────────

@event.listens_for(LedgerEntry, "before_update")
def _block_ledger_update(mapper, connection, target):
    raise RuntimeError(
        f"LedgerEntry id={target.id} seq={target.sequence_number} is IMMUTABLE. "
        "To correct a mistake, post a reversal entry with a new correlation_id."
    )


@event.listens_for(LedgerEntry, "before_delete")
def _block_ledger_delete(mapper, connection, target):
    raise RuntimeError(
        f"LedgerEntry id={target.id} seq={target.sequence_number} cannot be deleted. "
        "The financial ledger is append-only."
    )
