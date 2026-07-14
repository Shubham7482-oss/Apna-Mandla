from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, schemas
from app.core.database import get_db
from app.core.auth import get_current_active_user
from app.models.user import User

router = APIRouter()

@router.post("/seller", response_model=schemas.RoleApplicationOut)
def apply_for_seller(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    application_in: schemas.RoleApplicationCreate,
):
    """
    Submit an application to become a Seller.
    """
    # TODO: Add logic to check if user already has the role or an existing application
    application = crud.crud_role_application.create_application(
        db=db, 
        user_id=current_user.id, 
        requested_role='SELLER', 
        details=application_in.details
    )
    return application

@router.post("/rider", response_model=schemas.RoleApplicationOut)
def apply_for_rider(
    *,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    application_in: schemas.RoleApplicationCreate,
):
    """
    Submit an application to become a Rider.
    """
    # TODO: Add logic to check if user already has the role or an existing application
    application = crud.crud_role_application.create_application(
        db=db, 
        user_id=current_user.id, 
        requested_role='RIDER', 
        details=application_in.details
    )
    return application
