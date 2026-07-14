from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from app.core.database import get_db
from app.models.udhar import UdharAgreement
from app.schemas.udhar import UdharAgreementCreate, UdharAgreementStatusUpdate, UdharAgreement as UdharAgreementSchema

router = APIRouter()

# ... (previous functions are here) ...

@router.post("/udhar/agreement/{agreement_id}/approve_change", response_model=UdharAgreementSchema)
def approve_udhar_change(agreement_id: int, approved: bool = Body(..., embed=True), approver: str = Body(..., embed=True, pattern="^(seller|customer)$"), db: Session = Depends(get_db)):
    """
    The other party approves or rejects the requested changes.
    """
    db_udhar_agreement = db.query(UdharAgreement).filter(UdharAgreement.id == agreement_id).first()

    if not db_udhar_agreement:
        raise HTTPException(status_code=404, detail="Udhar agreement not found.")

    # Check if the agreement is actually pending the approver's action
    is_pending_seller = db_udhar_agreement.status == 'pending_seller_approval' and approver == 'seller'
    is_pending_customer = db_udhar_agreement.status == 'pending_customer_approval' and approver == 'customer'

    if not is_pending_seller and not is_pending_customer:
        raise HTTPException(status_code=400, detail=f"This agreement is not awaiting approval from {approver}.")

    if approved:
        # Apply pending changes to the main fields
        if db_udhar_agreement.pending_credit_limit is not None:
            db_udhar_agreement.credit_limit = db_udhar_agreement.pending_credit_limit
            db_udhar_agreement.pending_credit_limit = None
            db_udhar_agreement.credit_limit_requested_by = None

        if db_udhar_agreement.pending_interest_rate is not None:
            db_udhar_agreement.interest_rate = db_udhar_agreement.pending_interest_rate
            db_udhar_agreement.pending_interest_rate = None
            db_udhar_agreement.interest_status = 'active'

        if db_udhar_agreement.pending_repayment_period is not None:
            db_udhar_agreement.repayment_period = db_udhar_agreement.pending_repayment_period
            db_udhar_agreement.pending_repayment_period = None
            db_udhar_agreement.repayment_status = 'active'
        
        db_udhar_agreement.status = "active"
    else:
        # Rejecting the changes: simply clear the pending fields and revert status
        db_udhar_agreement.pending_credit_limit = None
        db_udhar_agreement.credit_limit_requested_by = None
        db_udhar_agreement.pending_interest_rate = None
        # Revert status only if it wasn't changed by another pending item
        if db_udhar_agreement.interest_status.startswith('pending'):
            db_udhar_agreement.interest_status = 'active' if db_udhar_agreement.interest_rate else 'inactive'
        db_udhar_agreement.pending_repayment_period = None
        if db_udhar_agreement.repayment_status.startswith('pending'):
            db_udhar_agreement.repayment_status = 'active' if db_udhar_agreement.repayment_period else 'inactive'
        db_udhar_agreement.status = "active"

    db.commit()
    db.refresh(db_udhar_agreement)
    # Trigger notification to the requesting party
    return db_udhar_agreement
