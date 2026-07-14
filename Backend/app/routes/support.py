from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.rbac import require_support_admin
from app.models.complaint import Complaint
from app.models.user import User
from app.schemas.common import SuccessResponse

router = APIRouter(prefix="/support", tags=["Support & Complaints"])

@router.get("/all")
def list_complaints(
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_support_admin)
):
    """SUPPORT_ADMIN: List all complaints."""
    return db.query(Complaint).order_by(Complaint.created_at.desc()).all()

@router.patch("/{complaint_id}/resolve")
def resolve_complaint(
    complaint_id: int,
    note: str = Body(..., embed=True),
    status: str = Body("RESOLVED", embed=True),
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_support_admin)
):
    """SUPPORT_ADMIN: Mark a complaint as resolved or rejected."""
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(404, "Complaint not found")
    
    complaint.status = status
    complaint.admin_note = note
    db.commit()
    return SuccessResponse(success=True, message=f"Complaint marked as {status}")
