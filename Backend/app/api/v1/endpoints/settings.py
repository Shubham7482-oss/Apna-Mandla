
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.rbac import require_roles
from app.models.user import User
from app.crud.crud_setting import get_setting, create_or_update_setting
from typing import Any, Dict

router = APIRouter(prefix="/settings", tags=["Settings"])

@router.get("/{key}")
def read_setting(
    key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["super_admin"])),
):
    value = get_setting(db, key)
    if value is None:
        raise HTTPException(status_code=404, detail="Setting not found")
    return {"key": key, "value": value}

@router.post("/")
def write_setting(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["super_admin"])),
):
    key = payload.get("key")
    value = payload.get("value")
    if not key or value is None:
        raise HTTPException(status_code=400, detail="Key and value are required")

    setting = create_or_update_setting(db, key, value)
    return {"key": setting.key, "value": setting.value}
