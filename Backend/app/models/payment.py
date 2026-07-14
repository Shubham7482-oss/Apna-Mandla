# app/models/payment.py

from datetime import datetime
from sqlalchemy import String, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # 🔗 Relations
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    # 💰 Amount
    amount: Mapped[float] = mapped_column(Float, nullable=False)

    # 🔄 Payment lifecycle
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="INITIATED",
        index=True,
    )
    # INITIATED | SUCCESS | FAILED | REFUNDED

    # 🧾 Gateway fields
    transaction_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        unique=True,
    )

    failure_reason: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # 🕒 Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    refunded_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    # 🧠 Soft control
    is_archived: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    # 🔁 Relationships
    order: Mapped["Order"] = relationship(back_populates="payments")
    user: Mapped["User"] = relationship()

    def __repr__(self) -> str:
        return f"<Payment id={self.id} order_id={self.order_id} status={self.status}>"