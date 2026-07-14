from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.rider import Rider
from app.models.user import User

router = APIRouter(
    prefix="/riders",
    tags=["Riders"]
)


@router.post("/{rider_id}/duty")
def set_duty_status(
    rider_id: int,
    on_duty: bool = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # role check
    if current_user.user_type != "RIDER":
        raise HTTPException(status_code=403, detail="Not a rider")

    # fetch rider
    rider = (
        db.query(Rider)
        .filter(
            Rider.id == rider_id,
            Rider.user_id == current_user.id,
            Rider.is_archived == False,
        )
        .first()
    )

    if not rider:
        raise HTTPException(status_code=404, detail="Rider not found")

    if rider.blacklisted:
        raise HTTPException(status_code=403, detail="Rider is blocked")

    if rider.on_duty == on_duty:
        raise HTTPException(
            status_code=400,
            detail="Rider already in requested duty state",
        )

    if not on_duty and rider.current_order_id:
        raise HTTPException(
            status_code=400,
            detail="Cannot go off-duty while on active order",
        )

    # update duty
    rider.on_duty = on_duty

    if on_duty:
        rider.duty_started_at = datetime.utcnow()
    else:
        rider.last_duty_ended_at = datetime.utcnow()
        rider.current_order_id = None

    db.commit()
    db.refresh(rider)

    return {
        "message": "Duty status updated",
        "rider_id": rider.id,
        "on_duty": rider.on_duty,
    }