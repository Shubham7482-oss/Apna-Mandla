from sqlalchemy.orm import Session
from fastapi import Request
from app.models.audit_log import AuditLog


def log_action(
    db: Session,
    request: Request,
    action: str,
    description: str = None,
    user_id: int = None,
):
    audit = AuditLog(
        user_id=user_id,
        action=action,
        description=description,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )

    db.add(audit)
    db.commit()