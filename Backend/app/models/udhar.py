
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Numeric, Enum as SAEnum, Text
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import enum

from app.models.base import Base, TimestampMixin, SoftArchiveMixin


# ================================================
# 🔹 UDHAR AGREEMENT
# ================================================
class UdharAgreementStatus(str, enum.Enum):
    PENDING = "PENDING"        # Waiting for borrower's approval
    ACTIVE = "ACTIVE"          # Approved and in use
    REJECTED = "REJECTED"      # Borrower rejected the terms
    CANCELLED = "CANCELLED"    # Either party cancelled
    COMPLETED = "COMPLETED"    # Agreement term ended


class UdharAgreement(Base, TimestampMixin, SoftArchiveMixin):
    """
    Represents a credit agreement between a lender (e.g., Shop) and a borrower (e.g., Customer).
    """

    __tablename__ = "udhar_agreements"

    id = Column(Integer, primary_key=True, index=True)

    # Participants
    lender_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    borrower_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Agreement Terms
    credit_limit = Column(Numeric(10, 2), nullable=False)
    interest_rate = Column(Numeric(5, 2), default=0.0, nullable=False) # Annual interest rate
    start_date = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    end_date = Column(DateTime(timezone=True), nullable=True) # Optional end date
    
    # Status & Approval
    status = Column(SAEnum(UdharAgreementStatus), default=UdharAgreementStatus.PENDING, nullable=False, index=True)
    notes = Column(Text, nullable=True)

    # Relationships
    lender = relationship("User", foreign_keys=[lender_id], backref="lending_agreements")
    borrower = relationship("User", foreign_keys=[borrower_id], backref="borrowing_agreements")
    transactions = relationship("UdharTransaction", back_populates="agreement", cascade="all, delete-orphan")



# ================================================
# 🔹 UDHAR TRANSACTION
# ================================================
class UdharTransactionType(str, enum.Enum):
    DEBIT = "DEBIT"    # Borrower takes money (Udhar Liya)
    CREDIT = "CREDIT"  # Borrower pays back (Udhar Chukaya)
    INTEREST = "INTEREST" # Interest applied

class UdharTransaction(Base, TimestampMixin):
    """
    Represents a single transaction (debit or credit) within an UdharAgreement.
    """
    
    __tablename__ = "udhar_transactions"

    id = Column(Integer, primary_key=True, index=True)

    # Links
    agreement_id = Column(Integer, ForeignKey("udhar_agreements.id", ondelete="CASCADE"), nullable=False, index=True)

    # Transaction Details
    transaction_type = Column(SAEnum(UdharTransactionType), nullable=False, index=True)
    amount = Column(Numeric(10, 2), nullable=False)
    description = Column(String(255), nullable=True)
    
    # Optional link to a main order
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True)

    # Relationships
    agreement = relationship("UdharAgreement", back_populates="transactions")
    order = relationship("Order")

    __table_args__ = {'extend_existing': True}
