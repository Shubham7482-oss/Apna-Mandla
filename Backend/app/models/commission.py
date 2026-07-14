from datetime import datetime
from decimal import Decimal
from sqlalchemy import Boolean, Numeric, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CommissionConfig(Base):
    """
    Platform commission configuration.

    Rules:
    - Only ONE active commission config at a time.
    - Latest active config will be used.
    - Percent stored as Decimal (e.g., 10.00 means 10%).
    """

    __tablename__ = "commission_configs"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<CommissionConfig "
            f"id={self.id} "
            f"percent={self.percent} "
            f"active={self.is_active}>"
        )