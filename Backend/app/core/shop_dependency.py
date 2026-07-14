from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.shop import Shop


def get_current_shop(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Shop:
    """
    Ensures:
    - User is authenticated
    - User type is shop
    - Shop exists
    """

    if current_user.user_type != "shop":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only shop accounts allowed",
        )

    shop = db.query(Shop).filter(
        Shop.user_id == current_user.id
    ).first()

    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop profile not found",
        )

    if shop.suspended:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Shop is suspended",
        )

    return shop