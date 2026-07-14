from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import get_current_user, require_roles
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.user import User
from app.schemas.common import SuccessResponse


router = APIRouter(
    prefix="/rider-tasks",
    tags=["Rider Tasks"],
    dependencies=[Depends(require_roles(["rider"]))],
)

@router.post("/{order_id}/rider-pickup-from-shop")
def rider_confirm_pickup(    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):    pass
