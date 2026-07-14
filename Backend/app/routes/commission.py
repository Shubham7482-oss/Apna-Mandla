from app.core.auth import require_roles
from app.models.user import User
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select
from decimal import Decimal

from app.core.database import get_db
from app.core.rbac import require_roles
from app.models.commission import CommissionConfig

router = APIRouter(
    tags=["Commission Management"],
)


# ───────────────────────────────
# GET ACTIVE COMMISSION
# ───────────────────────────────
@router.get(
    "/commission",
    status_code=status.HTTP_200_OK,
)
def get_active_commission(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(["admin"])),
):

    commission = db.execute(
        select(CommissionConfig)
        .where(CommissionConfig.is_active == True)
        .order_by(CommissionConfig.created_at.desc())
    ).scalar_one_or_none()

    if not commission:
        raise HTTPException(
            status_code=404,
            detail="No active commission configuration found",
        )

    return {
        "commission_id": commission.id,
        "percent": str(commission.percent),
        "is_active": commission.is_active,
        "created_at": commission.created_at,
    }


# ───────────────────────────────
# SET NEW COMMISSION (ROTATION SAFE)
# ───────────────────────────────
@router.post(
    "/commission",
    status_code=status.HTTP_201_CREATED,
)
def set_new_commission(
    percent: Decimal,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(["admin"])),
):

    if percent <= Decimal("0.00") or percent > Decimal("100.00"):
        raise HTTPException(
            status_code=400,
            detail="Commission percent must be between 0 and 100",
        )

    try:
        # Lock current active config
        current_active = db.execute(
            select(CommissionConfig)
            .where(CommissionConfig.is_active == True)
            .with_for_update()
        ).scalar_one_or_none()

        # Deactivate old config
        if current_active:
            current_active.is_active = False

        # Create new config
        new_config = CommissionConfig(
            percent=percent,
            is_active=True,
        )

        db.add(new_config)

        db.commit()
        db.refresh(new_config)

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Commission update failed: {str(e)}",
        ) from e

    return {
        "message": "Commission updated successfully",
        "commission_id": new_config.id,
        "percent": str(new_config.percent),
    }
