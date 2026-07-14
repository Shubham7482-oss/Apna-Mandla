"""
app/models/udhar_account.py

UdharAccount — a credit line extended by a shop (lender) to a customer (borrower).

Design:
  • outstanding_balance is a CACHED value derived from UdharTransactions.
    It must ONLY be modified inside UdharService.
  • All real cash flows (repayment debiting customer wallet, crediting shop
    wallet) go through WalletService and produce LedgerEntry rows.
  • UdharTransaction records the credit events themselves
    (purchases on credit, repayments, interest accruals).
  • The accounting identity per account:
      SUM(UDHAR_DEBIT + UDHAR_INTEREST) - SUM(UDHAR_REPAYMENT) == outstanding_balance

Status lifecycle:
  PENDING  → lender created, awaiting borrower acceptance
  ACTIVE   → accepted and usable
  OVERDUE  → past due_days without full repayment (auto-flagged by scheduler)
  CLOSED   → fully repaid and closed
  SUSPENDED → manually suspended by lender or admin
"""

import enum
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey,
    Integer, Numeric, String, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class UdharAccountStatus(str, enum.Enum):
    PENDING   = "PENDING"
    ACTIVE    = "ACTIVE"
    OVERDUE   = "OVERDUE"
    CLOSED    = "CLOSED"
    SUSPENDED = "SUSPENDED"


class UdharAccount(Base, TimestampMixin):
    __tablename__ = "udhar_accounts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # ── Parties ───────────────────────────────────────────────────────────────
    # borrower_id: the customer who owes money
    borrower_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # lender_shop_id: the shop that extended credit (shop.id)
    lender_shop_id: Mapped[int] = mapped_column(
        ForeignKey("shops.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # ── Terms ─────────────────────────────────────────────────────────────────
    credit_limit:  Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    interest_rate: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), nullable=False, default=Decimal("0.0000")
    )  # Annual rate, e.g. 0.1200 = 12% p.a. — 0 means interest-free
    due_days:      Mapped[int]     = mapped_column(Integer, nullable=False, default=30)
    # Date after which account is considered overdue
    due_date:      Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Cached balance (always updated by UdharService) ───────────────────────
    outstanding_balance: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00")
    )

    # ── Status ────────────────────────────────────────────────────────────────
    status:       Mapped[str] = mapped_column(
        String(20), nullable=False,
        default=UdharAccountStatus.PENDING, index=True
    )
    is_active:    Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ── Interest tracking ─────────────────────────────────────────────────────
    last_interest_applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    total_interest_accrued:   Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00")
    )

    # ── Audit ─────────────────────────────────────────────────────────────────
    last_transaction_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_at:           Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Idempotency key for account creation (prevents double-open)
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    borrower     = relationship("User", foreign_keys=[borrower_id])
    lender_shop  = relationship("Shop", foreign_keys=[lender_shop_id], back_populates="udhar_accounts")
    transactions = relationship(
        "UdharTransaction",
        back_populates="udhar_account",
        cascade="all, delete-orphan",
        order_by="UdharTransaction.id",
    )
    # LedgerEntry rows that reference this account
    ledger_entries = relationship(
        "LedgerEntry",
        foreign_keys="LedgerEntry.udhar_account_id",
        back_populates="udhar_account",
    )

    # ── Constraints ───────────────────────────────────────────────────────────
    __table_args__ = (
        CheckConstraint("credit_limit > 0",                    name="ck_udhar_credit_limit_pos"),
        CheckConstraint("interest_rate >= 0",                  name="ck_udhar_interest_rate_nn"),
        CheckConstraint("outstanding_balance >= 0",            name="ck_udhar_outstanding_nn"),
        CheckConstraint("due_days > 0",                        name="ck_udhar_due_days_pos"),
        UniqueConstraint("borrower_id", "lender_shop_id",      name="uq_udhar_borrower_shop"),
    )

    def __repr__(self) -> str:
        return (
            f"<UdharAccount id={self.id} borrower={self.borrower_id} "
            f"shop={self.lender_shop_id} outstanding={self.outstanding_balance} "
            f"status={self.status}>"
        )

    @property
    def available_credit(self) -> Decimal:
        return max(Decimal("0.00"), self.credit_limit - self.outstanding_balance)

    @property
    def is_overdue(self) -> bool:
        if not self.due_date:
            return False
        return (
            self.outstanding_balance > 0
            and datetime.now(timezone.utc) > self.due_date
        )
