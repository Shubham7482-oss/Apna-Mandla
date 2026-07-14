from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.pincode import Pincode


def get_active_pincode(
    request: Request,
    db: Session = Depends(get_db),
) -> Pincode:
    """
    Resolve and validate the current active pincode from the request.

    - Extracts from `request.state.pin_code` (set by middleware).
    - Ensures the pincode exists and is serviceable.
    - Attaches `mandla_id` to `request.state` for downstream filters.
    """
    code = getattr(request.state, "pin_code", None)
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Active pincode missing. Pass X-Pincode header.",
        )

    pincode = (
        db.query(Pincode)
        .filter(
            Pincode.code == code,
            Pincode.is_archived == False,
            Pincode.is_active == True,
            Pincode.is_serviceable == True,
        )
        .first()
    )

    if not pincode:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Service not available in this pincode.",
        )

    # Cache for downstream handlers
    request.state.pincode = pincode
    request.state.mandla_id = pincode.mandla_id
    return pincode

