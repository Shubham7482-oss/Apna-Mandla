from app.core.auth import require_roles
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.rbac import require_roles
from app.models.mandla import Mandla
from app.models.user import User

router = APIRouter(prefix="/mandla", tags=["Mandla"])


# ───────────────────────────────
# CREATE MANDLA (ADMIN ONLY)
# ───────────────────────────────
@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
)
def create_mandla(
    name: str,
    state: str,
    current_user: User = Depends(require_roles(["admin"])),
    db: Session = Depends(get_db),
):
    existing = (
        db.query(Mandla)
        .filter(
            Mandla.name.ilike(name),
            Mandla.state.ilike(state),
            Mandla.is_archived == False,
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mandla already exists",
        )

    mandla = Mandla(
        name=name,
        state=state,
        is_active=True,
        is_archived=False,
    )

    db.add(mandla)
    db.commit()
    db.refresh(mandla)

    return {
        "id": mandla.id,
        "name": mandla.name,
        "state": mandla.state,
    }


# ───────────────────────────────
# LIST ALL MANDLAS (APP USE)
# ───────────────────────────────
@router.get("")
def list_mandlas(db: Session = Depends(get_db)):
    mandlas = (
        db.query(Mandla)
        .filter(
            Mandla.is_active == True,
            Mandla.is_archived == False,
        )
        .order_by(Mandla.name.asc())
        .all()
    )

    return [
        {
            "id": m.id,
            "name": m.name,
            "state": m.state,
        }
        for m in mandlas
    ]


# ───────────────────────────────
# SET MY MANDLA (USER / SHOP / RIDER)
# ───────────────────────────────
@router.post("/set")
def set_my_mandla(
    mandla_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    mandla = (
        db.query(Mandla)
        .filter(
            Mandla.id == mandla_id,
            Mandla.is_active == True,
            Mandla.is_archived == False,
        )
        .first()
    )

    if not mandla:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mandla not found",
        )

    current_user.mandla_id = mandla.id
    db.commit()

    return {
        "message": "Mandla set successfully",
        "mandla": {
            "id": mandla.id,
            "name": mandla.name,
            "state": mandla.state,
        },
    }


# ───────────────────────────────
# GET MY MANDLA
# ───────────────────────────────
@router.get("/me")
def get_my_mandla(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.mandla_id:
        return {"mandla": None}

    mandla = (
        db.query(Mandla)
        .filter(
            Mandla.id == current_user.mandla_id,
            Mandla.is_archived == False,
        )
        .first()
    )

    if not mandla:
        return {"mandla": None}

    return {
        "mandla": {
            "id": mandla.id,
            "name": mandla.name,
            "state": mandla.state,
        }
    }