# app/core/rbac.py

from typing import List, Union
from fastapi import Depends, HTTPException, status
from app.core.auth import get_current_user
from app.models.user import User


# ==========================================================
# 🔒 Generic Role Validator (Enterprise Ready)
# ==========================================================
def require_roles(
    allowed_roles: List[str],
):
    """
    Generic role-based access dependency.
    Supports single role or multiple roles.
    """

    if isinstance(allowed_roles, str):
        allowed_roles = [allowed_roles]

    allowed_roles = [role.lower() for role in allowed_roles]

    def role_checker(
        current_user: User = Depends(get_current_user),
    ) -> User:
        user_role = (current_user.user_type or "").lower()

        # Super admin override
        if user_role == "super_admin":
            return current_user

        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied for this role",
            )

        return current_user

    return role_checker


# ==========================================================
# 🔹 Specific Role Shortcuts (Backward Compatible)
# ==========================================================

def require_customer(
    current_user: User = Depends(get_current_user),
) -> User:
    return require_roles(["customer"])(current_user)


def require_shop(
    current_user: User = Depends(get_current_user),
) -> User:
    return require_roles(["shop"])(current_user)


def require_rider(
    current_user: User = Depends(get_current_user),
) -> User:
    return require_roles(["rider"])(current_user)


def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Allows ADMIN and SUPER_ADMIN
    """

    user_role = (current_user.user_type or "").lower()

    if user_role in ["admin", "super_admin"]:
        return current_user

    # Fallback to boolean flag if exists
    if getattr(current_user, "is_admin", False):
        return current_user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin access required",
    )


def require_super_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    STRICT: Allows ONLY SUPER_ADMIN. Blocks regular ADMINs.
    """
    user_role = (current_user.user_type or "").lower()

    if user_role == "super_admin":
        return current_user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Super Admin access required for this action",
    )


# ==========================================================
# 🔹 Admin Field-Level Security
# ==========================================================

def require_admin_field(field_role: str):
    """
    Field-level security for Admins.
    Allows SUPER_ADMIN always.
    Allows specified admin_role only.
    """
    def field_checker(current_user: User = Depends(get_current_user)) -> User:
        user_role = (current_user.user_type or "").upper()
        
        # 1. Super Admin is God Mode
        if user_role == "SUPER_ADMIN":
            return current_user
            
        # 2. Check if user is an ADMIN and has the correct field assigned
        admin_field = (getattr(current_user, "admin_role", "") or "").upper()
        if user_role == "ADMIN" and admin_field == field_role.upper():
            return current_user
            
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access Denied: You do not have permissions for {field_role} field."
        )
    return field_checker

# Helper instances for routes
require_shop_admin = require_admin_field("SHOP_ADMIN")
require_rider_admin = require_admin_field("RIDER_ADMIN")
require_user_admin = require_admin_field("USER_ADMIN")
require_finance_admin = require_admin_field("FINANCE_ADMIN")
require_content_admin = require_admin_field("CONTENT_ADMIN")
require_plan_admin = require_admin_field("PLAN_ADMIN")
require_support_admin = require_admin_field("SUPPORT_ADMIN")


# ==========================================================
# 🔹 Business Roles (Customer / Shop / Rider only)
# ==========================================================

def require_business_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Blocks ADMIN & SUPER_ADMIN.
    Allows CUSTOMER, SHOP, RIDER.
    """

    user_role = (current_user.user_type or "").lower()

    if user_role in ["customer", "shop", "rider"]:
        return current_user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Business account required",
    )