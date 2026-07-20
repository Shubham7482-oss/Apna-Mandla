
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from decimal import Decimal

from .user import User
from app.models.wallet import TransactionType


class WalletBase(BaseModel):
    balance: Decimal


class Wallet(WalletBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WalletTransactionBase(BaseModel):
    wallet_id: int
    transaction_type: TransactionType
    amount: Decimal
    order_id: Optional[int] = None
    udhar_transaction_id: Optional[int] = None


class WalletTransaction(WalletTransactionBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

