"""
app/schemas/user.py

Pydantic schemas for user-facing request/response validation.

Password policy (UserCreate / UserUpdate):
  - Minimum 8 characters.
  - Maximum 128 characters (bcrypt pre-hash handles the bcrypt 72-byte limit,
    but an upper bound prevents DoS via huge password strings).
  - Must contain at least one digit and one letter.
  - Common passwords are rejected at the route level via the validator.

Phone number:
  - 10–15 digits with optional leading + sign.
  - Whitespace is stripped before validation.
"""

import re
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# ─────────────────────────────────────────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────────────────────────────────────────

class UserType(str, Enum):
    customer = "CUSTOMER"
    shop = "SHOP"
    rider = "RIDER"
    admin = "ADMIN"
    govt = "GOVT"


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

_PHONE_RE = re.compile(r"^\+?[0-9]{10,15}$")

_COMMON_PASSWORDS = frozenset({
    "password", "password1", "12345678", "123456789", "1234567890",
    "qwerty123", "iloveyou", "admin1234", "letmein1",
})


def _validate_phone(v: str) -> str:
    v = v.strip()
    if not _PHONE_RE.match(v):
        raise ValueError(
            "Phone number must be 10–15 digits with an optional leading +. "
            "Example: +919876543210"
        )
    return v


def _validate_password(v: str) -> str:
    if len(v) > 128:
        raise ValueError("Password must be 128 characters or fewer.")
    if not any(c.isdigit() for c in v):
        raise ValueError("Password must contain at least one digit.")
    if not any(c.isalpha() for c in v):
        raise ValueError("Password must contain at least one letter.")
    if v.lower() in _COMMON_PASSWORDS:
        raise ValueError("Password is too common. Please choose a stronger password.")
    return v


# ─────────────────────────────────────────────────────────────────────────────
# REQUEST SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class UserBase(BaseModel):
    """Input schema for signup / user creation."""

    phone_number: str = Field(
        ...,
        min_length=10,
        max_length=16,         # +15 digits
        description="Phone number in international format, e.g. +919876543210",
    )
    email: Optional[EmailStr] = None
    name: Optional[str] = Field(None, min_length=2, max_length=150)
    user_type: UserType = UserType.customer

    @field_validator("phone_number", mode="before")
    @classmethod
    def clean_phone(cls, v: str) -> str:
        return _validate_phone(v)


class UserCreate(UserBase):
    """Extends UserBase with a required password for password-based signup."""

    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Password: 8–128 chars, must contain a letter and a digit.",
    )

    @field_validator("password", mode="after")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        return _validate_password(v)


class UserUpdate(BaseModel):
    """Partial-update schema — all fields optional."""

    email: Optional[EmailStr] = None
    name: Optional[str] = Field(None, min_length=2, max_length=150)
    password: Optional[str] = Field(None, min_length=8, max_length=128)

    @field_validator("password", mode="after")
    @classmethod
    def validate_password_strength(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _validate_password(v)


class DeviceTokenUpdate(BaseModel):
    """Update the FCM device token for push notifications."""
    device_token: str = Field(..., min_length=1, max_length=512)


# ─────────────────────────────────────────────────────────────────────────────
# RESPONSE SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class User(BaseModel):
    """Safe user representation returned to clients — no password fields."""

    id: int
    phone_number: str
    email: Optional[str] = None
    name: Optional[str] = None

    user_type: UserType
    phone_verified: bool
    email_verified: bool

    is_active: bool
    is_admin: bool
    is_govt: bool

    mandla_id: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
