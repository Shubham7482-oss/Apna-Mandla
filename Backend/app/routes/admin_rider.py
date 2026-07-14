
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rbac import require_rider_admin
from app.models.rider_profile import RiderProfile, RiderStatus
from app.models.user import User

router = APIRouter(
    prefix="/admin/riders", 
    tags=["Admin – Riders"],
    dependencies=[Depends(require_rider_admin)]
)


@router.get("/pending")
def list_pending_riders(
    admin: User = Depends(require_rider_admin),
    db: Session = Depends(get_db),
):
    query = db.query(RiderProfile).filter(RiderProfile.status == RiderStatus.PENDING)
    
    # Super admin sees all, field admin sees only their mandla
    if admin.user_type.lower() == "admin" and admin.mandla_id:
        query = query.filter(RiderProfile.mandla_id == admin.mandla_id)

    riders = query.all()

    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "mandla_id": r.mandla_id,
            "vehicle_type": r.vehicle_type,
            "license_number": r.license_number,
            "status": r.status,
        }
        for r in riders
    ]


@router.post("/{rider_profile_id}/approve")
def approve_rider(
    rider_profile_id: int,
    admin: User = Depends(require_rider_admin),
    db: Session = Depends(get_db),
):
    profile = (
        db.query(RiderProfile)
        .filter(RiderProfile.id == rider_profile_id)
        .first()
    )

    if not profile:
        raise HTTPException(status_code=404, detail="Rider profile not found")
        
    # Area check for field admin
    if admin.user_type.lower() == "admin" and admin.mandla_id and profile.mandla_id != admin.mandla_id:
        raise HTTPException(status_code=403, detail="You do not have permission to approve riders in this area.")

    if profile.status != RiderStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail="Rider is not in pending state",
        )

    # approve rider profile
    profile.status = RiderStatus.APPROVED
    profile.is_active = True

    # promote user role
    user = db.query(User).filter(User.id == profile.user_id).first()
    if user:
        user.user_type = "RIDER"

    db.commit()

    return {
        "message": "Rider approved",
        "user_id": user.id if user else None,
        "new_role": user.user_type if user else None,
    }


@router.post("/{rider_profile_id}/reject")
def reject_rider(
    rider_profile_id: int,
    admin: User = Depends(require_rider_admin),
    db: Session = Depends(get_db),
):
    profile = (
        db.query(RiderProfile)
        .filter(RiderProfile.id == rider_profile_id)
        .first()
    )

    if not profile:
        raise HTTPException(status_code=404, detail="Rider profile not found")
        
    # Area check for field admin
    if admin.user_type.lower() == "admin" and admin.mandla_id and profile.mandla_id != admin.mandla_id:
        raise HTTPException(status_code=403, detail="You do not have permission to reject riders in this area.")

    if profile.status != RiderStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail="Rider is not in pending state",
        )

    profile.status = RiderStatus.REJECTED
    profile.is_active = False

    db.commit()

    return {"message": "Rider rejected"}
