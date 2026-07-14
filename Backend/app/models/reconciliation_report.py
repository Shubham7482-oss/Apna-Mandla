"""
app/models/reconciliation_report.py

Stores results of each reconciliation run.
Reports are append-only (no update/delete).
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ReconciliationReport(Base):
    __tablename__ = "reconciliation_reports"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Who triggered it (NULL = scheduled job)
    triggered_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False)  # SCHEDULED | MANUAL

    # Summary
    total_entries:       Mapped[int]     = mapped_column(Integer, nullable=False, default=0)
    wallets_checked:     Mapped[int]     = mapped_column(Integer, nullable=False, default=0)
    correlations_checked:Mapped[int]     = mapped_column(Integer, nullable=False, default=0)
    issues_found:        Mapped[int]     = mapped_column(Integer, nullable=False, default=0)
    is_clean:            Mapped[bool]    = mapped_column(Boolean, nullable=False, default=True)

    # Aggregate balances at time of run
    total_cr_sum:        Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0.00"))
    total_dr_sum:        Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0.00"))

    # Full JSON detail for analysis (array of issue strings)
    issues_json:         Mapped[str | None] = mapped_column(Text, nullable=True)

    # Duration in milliseconds
    duration_ms:         Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    triggered_by = relationship("User", foreign_keys=[triggered_by_id])

    def __repr__(self) -> str:
        return (
            f"<ReconciliationReport id={self.id} clean={self.is_clean} "
            f"issues={self.issues_found} at={self.created_at}>"
        )
