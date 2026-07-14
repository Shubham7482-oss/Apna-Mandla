# app/routes/users.py

from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.models.mini_website import MiniWebsite
from app.utils.role_resolver import get_role_list, get_current_role
from app.utils.qr_generator import generate_qr

router = APIRouter(tags=["Users"])


def _serialize_user_with_roles(db: Session, user: User) -> dict:
    roles = get_role_list(db, user)
    current_role = get_current_role(user)
    
    website = (
        db.query(MiniWebsite)
        .filter(
            MiniWebsite.user_id == user.id,
            MiniWebsite.is_archived == False,
        )
        .first()
    )

    if not user.qr_code_url:
        qr_path = generate_qr(user.unique_id)
        user.qr_code_url = qr_path
        db.commit()
        db.refresh(user)

    return {
        "id": user.id,
        "phone_number": user.phone_number,
        "email": user.email,
        "name": getattr(user, "name", None),
        "user_type": user.user_type,
        "roles": roles,
        "current_role": current_role,
        "phone_verified": user.phone_verified,
        "email_verified": user.email_verified,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "qr_code_url": user.qr_code_url,
        "website_slug": website.slug if website else None,
    }


# ───────────────────────────────
# GET MY PROFILE (APP CORE API)
# ───────────────────────────────
@router.get("/me")
def get_my_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _serialize_user_with_roles(db, current_user)


# ───────────────────────────────
# UPDATE MY PROFILE (APP CORE API)
# ───────────────────────────────
@router.patch("/me")
def update_my_profile(
    name: Optional[str] = None,
    email: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    App onboarding / profile completion API.

    RULES:
    - Phone number NEVER editable
    - User type is treated as current active role, not role list
    - Email change resets verification
    """

    if name is not None:
        # `User` already has a name column; keep this update simple.
        current_user.name = name

    if email is not None and email != current_user.email:
        existing = (
            db.query(User)
            .filter(User.email == email, User.id != current_user.id)
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Email already in use",
            )
        current_user.email = email
        current_user.email_verified = False

    db.commit()
    db.refresh(current_user)

    return _serialize_user_with_roles(db, current_user)


# ───────────────────────────────
# SWITCH ACTIVE ROLE (NO LOGOUT)
# ───────────────────────────────
@router.post("/switch-role")
def switch_active_role(
    role: Literal["customer", "seller", "rider", "admin", "super_admin"],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Change current active role for the logged-in user without requiring logout.

    Roles are validated against derived capabilities:
    - customer: always allowed
    - seller: requires an approved shop
    - rider: requires an approved rider profile
    - admin / super_admin: requires corresponding flags on user
    """
    roles = get_role_list(db, current_user)
    if role not in roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Role '{role}' is not assigned to this account",
        )

    # Admins cannot switch down to non-admin roles via this endpoint.
    current_type = (current_user.user_type or "").upper()
    is_admin_like = current_type in {"ADMIN", "SUPER_ADMIN"}
    is_target_admin_like = role in {"admin", "super_admin"}

    if is_admin_like and role in {"customer", "seller", "rider"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins cannot switch to non-admin roles from this endpoint.",
        )

    # Prevent privilege escalation: switching to admin/super_admin is not allowed
    # via this endpoint; must go through promotion flows.
    if not is_admin_like and is_target_admin_like:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot switch into admin roles via this endpoint.",
        )

    # Persist the active role using existing `user_type` column so that
    # the rest of the system (RBAC, dashboards, etc.) keeps working.
    mapping = {
        "customer": "CUSTOMER",
        "seller": "SHOP",
        "rider": "RIDER",
        "admin": "ADMIN",
        "super_admin": "SUPER_ADMIN",
    }
    current_user.user_type = mapping[role]
    db.commit()
    db.refresh(current_user)

    return _serialize_user_with_roles(db, current_user)