from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime
from decimal import Decimal

from .user import User
from app.models.udhar import UdharAgreementStatus
from app.models.udhar_transaction import UdharTxType

# ================================================
# 🔹 UDHAR AGREEMENT SCHEMAS
# ================================================

class UdharAgreementBase(BaseModel):
    lender_id: int
    borrower_id: int
    credit_limit: Decimal
    interest_rate: Optional[Decimal] = Decimal("0.0")
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    notes: Optional[str] = None


class UdharAgreementCreate(UdharAgreementBase):
    pass


class UdharAgreementStatusUpdate(BaseModel):
    status: UdharAgreementStatus


class UdharAgreement(UdharAgreementBase):
    id: int
    status: UdharAgreementStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ================================================
# 🔹 UDHAR TRANSACTION SCHEMAS
# ================================================

class UdharTransactionBase(BaseModel):
    agreement_id: int
    transaction_type: UdharTxType
    amount: Decimal
    description: Optional[str] = None
    order_id: Optional[int] = None


class UdharTransactionCreate(UdharTransactionBase):
    pass


class UdharTransaction(UdharTransactionBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ================================================
# 🔹 FULL UDHAR DETAILS (For detailed views)
# ================================================

class UdharAgreementWithDetails(UdharAgreement):
    lender: User
    borrower: User
    transactions: List[UdharTransaction] = []
