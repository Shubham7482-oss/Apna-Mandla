
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, models
from app import schemas
from app.api import deps

router = APIRouter()


@router.get("/me", response_model=schemas.user.User)
def read_users_me(current_user: models.User = Depends(deps.get_current_active_user)) -> any:
    """
    Get current user.
    """
    return current_user

@router.patch("/me/device-token", response_model=schemas.user.User)
def update_device_token(
    *, 
    db: Session = Depends(deps.get_db), 
    device_token_in: schemas.user.DeviceTokenUpdate,
    current_user: models.User = Depends(deps.get_current_active_user)
):
    """
    Update device token for the current user.
    """
    current_user.device_token = device_token_in.device_token
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return current_user

