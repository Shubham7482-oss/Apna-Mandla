from sqlalchemy.orm import Session

from app.models.shop import Shop
from app.models.rider_profile import RiderProfile
from app.models.user import User


def resolve_user_roles(db: Session, user: User) -> dict:
    """
    Legacy helper returning boolean flags for common roles.

    NOTE: Prefer using `get_role_list` / `get_current_role` for new code.
    """
    is_seller = (
        db.query(Shop)
        .filter(Shop.user_id == user.id)
        .first()
        is not None
    )

    is_rider = (
        db.query(RiderProfile)
        .filter(RiderProfile.user_id == user.id)
        .first()
        is not None
    )

    return {
        "is_customer": True,
        "is_seller": is_seller,
        "is_rider": is_rider,
        "is_admin": getattr(user, "is_admin", False),
    }


def get_role_list(db: Session, user: User) -> list[str]:
    """
    Normalized role list for the account, independent of current active role.

    Roles follow API naming:
    - customer
    - seller
    - rider
    - admin
    - super_admin
    """
    flags = resolve_user_roles(db, user)
    roles: list[str] = ["customer"]

    if flags.get("is_seller"):
        roles.append("seller")
    if flags.get("is_rider"):
        roles.append("rider")

    user_type = (getattr(user, "user_type", "") or "").upper()
    if user_type == "SUPER_ADMIN":
        roles.append("super_admin")
    elif getattr(user, "is_admin", False) or user_type == "ADMIN":
        roles.append("admin")

    # De-duplicate while preserving order
    seen: set[str] = set()
    unique_roles: list[str] = []
    for r in roles:
        if r not in seen:
            seen.add(r)
            unique_roles.append(r)
    return unique_roles


def get_current_role(user: User) -> str:
    """
    Derive current active role for the account.

    For now we map directly from `user_type` (DB column) to the API role
    string and treat it as the active role.
    """
    user_type = (getattr(user, "user_type", "") or "").upper()

    if user_type == "SHOP":
        return "seller"
    if user_type == "RIDER":
        return "rider"
    if user_type == "SUPER_ADMIN":
        return "super_admin"
    if user_type == "ADMIN":
        return "admin"

    # Default / fallback
    return "customer"
