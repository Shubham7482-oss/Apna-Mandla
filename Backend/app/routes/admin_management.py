from fastapi import APIRouter, Depends, HTTPException, status, Request, Body
from sqlalchemy.orm import Session
from typing import Optional, List, Any
from pydantic import BaseModel
from datetime import datetime, timezone

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.rbac import require_user_admin, require_super_admin
from app.models.user import User
from app.models.shop_profile import ShopProfile
from app.models.rider_profile import RiderProfile
from app.models.wallet import Wallet
from app.models.ledger_entry import LedgerEntry
from decimal import Decimal
from app.services.admin_audit_service import log_admin_action

router = APIRouter(prefix="/admin/manage", tags=["Admin Management"])


# ───────────────────────────────
# SCHEMAS
# ───────────────────────────────
class RejectionRequest(BaseModel):
    reason: str = "Documents not clear or invalid information provided."


class AdminCreateRequest(BaseModel):
    user_id: int
    role: str


class WalletRechargeRequest(BaseModel):
    shop_id: int
    amount: Decimal  # Use Decimal for currency/financial values
    description: Optional[str] = "Admin Manual Recharge"


# ───────────────────────────────
# PERMISSION GUARD
# ───────────────────────────────
def check_admin_permission(required_role: str, user: User):
    if user.user_type == "SUPER_ADMIN":
        return True
    if user.is_admin and user.admin_role == required_role:
        return True
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Aapke paas {required_role} ki permission nahi hai.",
    )


# ───────────────────────────────
# 👑 SUPER ADMIN: MANAGE ADMINS
# ───────────────────────────────
@router.post("/promote-admin", response_model=None)
def promote_to_admin(
    data: AdminCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
    request: Request = None,
):
    target_user = db.query(User).filter(User.id == data.user_id).first()
    if not target_user:
        raise HTTPException(404, "User nahi mila")

    target_user.is_admin = True
    target_user.user_type = "ADMIN"
    target_user.admin_role = data.role
    db.commit()

    ip = request.client.host if request and request.client else None

    log_admin_action(
        db=db,
        admin_id=current_user.id,
        module="admin_management",
        action=f"PROMOTE_ADMIN:{data.role}",
        target_id=str(target_user.id),
        ip_address=ip,
    )

    return {"message": f"User {target_user.phone_number} ab {data.role} ban gaya hai"}


# ───────────────────────────────
# 👤 USER ADMIN: MANAGE USERS
# ───────────────────────────────
@router.get("/users")
def list_all_users(
    role: Optional[str] = None,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_user_admin)
):
    """USER_ADMIN: List all registered users."""
    query = db.query(User)
    if role:
        query = query.filter(User.user_type == role.upper())
    return query.order_by(User.created_at.desc()).all()

@router.patch("/users/{user_id}/status")
def toggle_user_active_status(
    user_id: int,
    is_active: bool = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_user_admin)
):
    """USER_ADMIN: Block or Unblock a user."""
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(404, "User not found")
    
    if target_user.user_type == "SUPER_ADMIN":
        raise HTTPException(403, "Cannot change status of Super Admin")
        
    target_user.is_active = is_active
    db.commit()
    return {"success": True, "message": f"User status set to {is_active}"}


# ───────────────────────────────
# 🏪 SHOP ADMIN
# ───────────────────────────────
@router.post("/shops/{shop_id}/approve", response_model=None)
def approve_shop(
    shop_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_user),
    request: Request = None,
):
    check_admin_permission("SHOP_ADMIN", admin)

    shop = db.query(ShopProfile).filter(ShopProfile.id == shop_id).first()
    if not shop:
        raise HTTPException(404, "Shop nahi mili")

    shop.approval_status = "APPROVED"
    shop.rejection_reason = None

    owner = db.query(User).filter(User.id == shop.user_id).first()
    owner.user_type = "SHOP"

    db.commit()

    ip = request.client.host if request and request.client else None

    log_admin_action(
        db=db,
        admin_id=admin.id,
        module="admin_management",
        action="APPROVE_SHOP",
        target_id=str(shop_id),
        ip_address=ip,
    )

    return {"message": "Shop approve ho gayi hai."}


@router.post("/shops/{shop_id}/reject", response_model=None)
def reject_shop(
    shop_id: int,
    data: RejectionRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_user),
    request: Request = None,
):
    check_admin_permission("SHOP_ADMIN", admin)

    shop = db.query(ShopProfile).filter(ShopProfile.id == shop_id).first()
    if not shop:
        raise HTTPException(404, "Shop nahi mili")

    shop.approval_status = "REJECTED"
    shop.rejection_reason = data.reason
    db.commit()

    ip = request.client.host if request and request.client else None

    log_admin_action(
        db=db,
        admin_id=admin.id,
        module="admin_management",
        action="REJECT_SHOP",
        target_id=str(shop_id),
        ip_address=ip,
    )

    return {"message": "Shop reject kar di gayi hai.", "reason": data.reason}


# ───────────────────────────────
# 🏍️ RIDER ADMIN
# ───────────────────────────────
@router.post("/riders/{rider_id}/approve", response_model=None)
def approve_rider(
    rider_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_user),
    request: Request = None,
):
    check_admin_permission("RIDER_ADMIN", admin)

    rider = db.query(RiderProfile).filter(RiderProfile.id == rider_id).first()
    if not rider:
        raise HTTPException(404, "Rider nahi mila")

    rider.status = "APPROVED"
    rider.rejection_reason = None

    rider_user = db.query(User).filter(User.id == rider.user_id).first()
    rider_user.user_type = "RIDER"

    db.commit()

    ip = request.client.host if request and request.client else None

    log_admin_action(
        db=db,
        admin_id=admin.id,
        module="admin_management",
        action="APPROVE_RIDER",
        target_id=str(rider_id),
        ip_address=ip,
    )

    return {"message": "Rider approve ho gaya hai."}


@router.post("/riders/{rider_id}/reject", response_model=None)
def reject_rider(
    rider_id: int,
    data: RejectionRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_user),
    request: Request = None,
):
    check_admin_permission("RIDER_ADMIN", admin)

    rider = db.query(RiderProfile).filter(RiderProfile.id == rider_id).first()
    if not rider:
        raise HTTPException(404, "Rider nahi mila")

    rider.status = "REJECTED"
    rider.rejection_reason = data.reason
    db.commit()

    ip = request.client.host if request and request.client else None

    log_admin_action(
        db=db,
        admin_id=admin.id,
        module="admin_management",
        action="REJECT_RIDER",
        target_id=str(rider_id),
        ip_address=ip,
    )

    return {"message": "Rider profile reject kar di gayi hai.", "reason": data.reason}


# ───────────────────────────────
# 💰 WALLET RECHARGE
# ───────────────────────────────
@router.post("/wallets/recharge", response_model=None)
def recharge_shop_wallet(
    data: WalletRechargeRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_user),
    request: Request = None,
):
    if admin.user_type != "SUPER_ADMIN":
        check_admin_permission("ACCOUNTS_ADMIN", admin)

    if data.amount <= 0:
        raise HTTPException(400, "Amount 0 se bada hona chahiye.")

    wallet = db.query(Wallet).filter(
        Wallet.owner_type == "SHOP",
        Wallet.owner_id == data.shop_id,
    ).first()

    if not wallet:
        raise HTTPException(404, "Is shop ka wallet nahi mila.")

    try:
        # Ensure wallet balance is also Decimal
        wallet.balance += data.amount 

        db.add(
            LedgerEntry(
                wallet_id=wallet.id,
                entry_type="CREDIT",
                amount=data.amount, # This should be Decimal
                description=data.description,
            )
        )

        db.commit()

        ip = request.client.host if request and request.client else None

        log_admin_action(
            db=db,
            admin_id=admin.id,
            module="admin_management",
            action="WALLET_RECHARGE",
            target_id=str(data.shop_id),
            ip_address=ip,
        )

        return {
            "status": "success",
            "shop_id": data.shop_id,
            "new_balance": wallet.balance,
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Error: {str(e)}")