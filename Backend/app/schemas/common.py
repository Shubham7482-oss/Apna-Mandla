# backend/app/schemas/common.py

from typing import Generic, TypeVar, Optional
from pydantic import BaseModel
from pydantic.generics import GenericModel


T = TypeVar("T")


# ==========================================================
# 🔹 Standard Success Response Wrapper
# ==========================================================
class SuccessResponse(GenericModel, Generic[T]):
    success: bool = True
    data: T
    message: Optional[str] = None


# ==========================================================
# 🔹 Standard Error Response Schema (Optional Usage)
# ==========================================================
class ErrorResponse(BaseModel):
    success: bool = False
    message: str
    error_code: Optional[str] = None


# ==========================================================
# 🔹 Simple Message Response (No Data)
# ==========================================================
class MessageResponse(BaseModel):
    success: bool = True
    message: str