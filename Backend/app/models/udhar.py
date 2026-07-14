from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    DateTime,
    Numeric,
    Enum as SAEnum,
    Text,
)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import enum

from app.models.base import Base, TimestampMixin, SoftArchiveMixin


# =====================================================
# UDHAR AGREEMENT
# =====================================================

class UdharAgreementStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class UdharAgreement(Base, TimestampMixin, SoftArchiveMixin):
    """
    Represents a credit agreement between a lender and borrower.

    NOTE:
    Transaction records are handled by app/models/udhar_transaction.py
    """

    __tablename__ = "udhar_agreements"

    id = Column(Integer, primary_key=True, index=True)

    lender_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    borrower_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    credit_limit = Column(Numeric(10, 2), nullable=False)

    interest_rate = Column(
        Numeric(5, 2),
        default=0.0,
        nullable=False,
    )

    start_date = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    end_date = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    status = Column(
        SAEnum(UdharAgreementStatus),
        default=UdharAgreementStatus.PENDING,
        nullable=False,
        index=True,
    )

    notes = Column(Text, nullable=True)

    # Relationships

    lender = relationship(
        "User",
        foreign_keys=[lender_id],
        backref="lending_agreements",
    )

    borrower = relationship(
        "User",
        foreign_keys=[borrower_id],
        backref="borrowing_agreements",
    )
