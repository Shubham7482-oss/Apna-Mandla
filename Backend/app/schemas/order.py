# app/schemas/order.py

from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from enum import Enum


class OrderCategory(str, Enum):
    HIRE_PERSON = "HIRE_PERSON"
    DELIVERY = "DELIVERY"
    RENT = "RENT"
    CONTRACTOR = "CONTRACTOR"
    KHANDANI_PESHA = "KHANDANI_PESHA"
    OTHER = "OTHER"


class OrderStatus(str, Enum):
    CREATED = "CREATED"
    CONFIRMED = "CONFIRMED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class OrderCreate(BaseModel):
    customer_profile_id: int
    category: OrderCategory
    location_text: Optional[str] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    estimated_amount: Optional[float] = None


class OrderResponse(BaseModel):
    order_id: int
    order_number: str
    category: OrderCategory
    status: OrderStatus
    customer_id: int
    provider_user_id: Optional[int]
    location_text: Optional[str]
    scheduled_start: Optional[datetime]
    scheduled_end: Optional[datetime]
    estimated_amount: Optional[float]
    final_amount: Optional[float]
    created_at: datetime

    class Config:
        from_attributes = True
