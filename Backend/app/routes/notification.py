from app.core.auth import require_roles
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Any

from app.core.database import get_db
from app.core.auth import get_current_user  # ✅ FIXED
from app.models.user import User
from app.models.notification import Notification
from app.core.websocket_manager import manager


router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"],
)


# =========================================================
# INTERNAL HELPER – SAVE + SEND
# =========================================================
async def _send_notification(
    db: Session,
    user_id: int,
    title: str,
    message: str,
    event_type: str = "GENERAL",
) -> None:

    # 1️⃣ Save to DB
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        event_type=event_type,
    )

    db.add(notification)
    db.commit()
    db.refresh(notification)

    # 2️⃣ Console Log
    print(f"[NOTIFICATION] user={user_id} | {title} → {message}")

    # 3️⃣ WebSocket Push (fail-safe)
    try:
        await manager.send_to_user(
            str(user_id),
            {
                "event": "NOTIFICATION",
                "data": {
                    "id": notification.id,
                    "title": title,
                    "message": message,
                    "event_type": event_type,
                    "timestamp": notification.created_at.isoformat(),
                },
            },
        )
    except Exception as e:
        print(f"[WS ERROR] {e}")


# =========================================================
# ADMIN → SEND TEST NOTIFICATION
# =========================================================
@router.post("/admin/send")
async def admin_send_notification(
    user_id: int,
    title: str,
    message: str,
    current_admin: Any = Depends(require_roles(["admin"])),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    await _send_notification(
        db=db,
        user_id=user.id,
        title=title,
        message=message,
        event_type="ADMIN",
    )

    return {
        "success": True,
        "message": "Notification saved & sent",
        "user_id": user.id,
    }


# =========================================================
# GET MY NOTIFICATIONS (USER ONLY)
# =========================================================
@router.get("/my")
def get_my_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),  # ✅ FIXED
):
    notifications = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )

    return notifications