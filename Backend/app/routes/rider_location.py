from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime

from app.core.database import get_db
from app.models.user import User
from app.core.auth import get_current_user, require_roles
from app.models.rider_profile import RiderProfile

router = APIRouter()

class RiderLocationUpdate(BaseModel):
    plus_code: str

@router.put("/rider/location", status_code=204)
def update_rider_location(
    location_data: RiderLocationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _=Depends(require_roles(["rider"]))
):
    """
    Updates the current geographical location of the rider.
    """
    rider_profile = db.query(RiderProfile).filter(RiderProfile.user_id == current_user.id).first()

    if not rider_profile:
        raise HTTPException(status_code=404, detail="Rider profile not found.")

    rider_profile.current_plus_code = location_data.plus_code
    rider_profile.last_location_update = datetime.utcnow()
    
    db.commit()

    return
