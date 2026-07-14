
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app import models, schemas
from app.api import deps

router = APIRouter()

# ================================================
# 🔹 UDHAR AGREEMENTS
# ================================================

@router.post("/udhar/agreements/", response_model=schemas.UdharAgreement, status_code=status.HTTP_201_CREATED)
def create_udhar_agreement(
    *, 
    db: Session = Depends(deps.get_db), 
    agreement_in: schemas.UdharAgreementCreate, 
    current_user: models.User = Depends(deps.get_current_active_user)
):
    """
    Create a new Udhar Agreement. The user creating it is the lender.
    """
    # Ensure the lender is the current user
    if agreement_in.lender_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only create agreements for yourself.")

    # TODO: Add more validation (e.g., does borrower exist?)
    
    agreement = models.UdharAgreement(**agreement_in.dict())
    db.add(agreement)
    db.commit()
    db.refresh(agreement)
    return agreement


@router.get("/udhar/agreements/", response_model=List[schemas.UdharAgreement])
def get_user_udhar_agreements(
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
    as_lender: bool = False,
    as_borrower: bool = False,
):
    """
    Get all udhar agreements for the current user.
    """
    query = db.query(models.UdharAgreement)
    if as_lender:
        return query.filter(models.UdharAgreement.lender_id == current_user.id).all()
    if as_borrower:
        return query.filter(models.UdharAgreement.borrower_id == current_user.id).all()
    
    # If no filter specified, return all related agreements
    return query.filter(
        (models.UdharAgreement.lender_id == current_user.id) | 
        (models.UdharAgreement.borrower_id == current_user.id)
    ).all()

@router.patch("/udhar/agreements/{agreement_id}/status", response_model=schemas.UdharAgreement)
def update_agreement_status(
    agreement_id: int,
    status_update: schemas.UdharAgreementStatusUpdate,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """
    Update the status of an udhar agreement (e.g., to ACTIVE or REJECTED).
    Only the borrower can activate/reject.
    """
    agreement = db.query(models.UdharAgreement).filter(models.UdharAgreement.id == agreement_id).first()
    if not agreement:
        raise HTTPException(status_code=404, detail="Agreement not found.")

    # Check permissions
    if agreement.borrower_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the borrower can update the status.")

    agreement.status = status_update.status
    db.commit()
    db.refresh(agreement)
    return agreement

# ================================================
# 🔹 UDHAR TRANSACTIONS
# ================================================

@router.post("/udhar/transactions/", response_model=schemas.UdharTransaction, status_code=status.HTTP_201_CREATED)
def create_udhar_transaction(
    *, 
    db: Session = Depends(deps.get_db), 
    transaction_in: schemas.UdharTransactionCreate,
    current_user: models.User = Depends(deps.get_current_active_user)
):
    """
    Record a new transaction (debit or credit) under an agreement.
    """
    agreement = db.query(models.UdharAgreement).filter(models.UdharAgreement.id == transaction_in.agreement_id).first()
    if not agreement:
        raise HTTPException(status_code=404, detail="Agreement not found.")

    # Security: Ensure only the lender can add DEBIT transactions
    if transaction_in.transaction_type == models.UdharTransactionType.DEBIT and agreement.lender_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the lender can record a debit.")

    # Security: Ensure only the borrower can add CREDIT transactions (repayments)
    if transaction_in.transaction_type == models.UdharTransactionType.CREDIT and agreement.borrower_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the borrower can record a repayment.")

    # TODO: Check if transaction exceeds credit limit

    transaction = models.UdharTransaction(**transaction_in.dict())
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction

@router.get("/udhar/agreements/{agreement_id}/transactions", response_model=List[schemas.UdharTransaction])
def get_agreement_transactions(
    agreement_id: int,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """
    Get all transactions for a specific agreement.
    """
    agreement = db.query(models.UdharAgreement).filter(models.UdharAgreement.id == agreement_id).first()
    if not agreement or (agreement.lender_id != current_user.id and agreement.borrower_id != current_user.id):
        raise HTTPException(status_code=404, detail="Agreement not found or access denied.")

    return agreement.transactions

