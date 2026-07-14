from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from decimal import Decimal

from app.core.database import get_db
from app.models.udhar_account import UdharAccount
from app.models.udhar_transaction import UdharTransaction
from app.schemas.udhar import UdharTransactionCreate, UdharTransaction as UdharTransactionSchema

router = APIRouter()

# ... (previous functions are here) ...

@router.post("/udhar/transaction/{transaction_id}/reject", response_model=UdharTransactionSchema)
def reject_transaction(transaction_id: int, rejector: str = Body(..., embed=True, pattern="^(seller|customer)$"), db: Session = Depends(get_db)):
    """
    Reject a pending transaction.
    """
    db_transaction = db.query(UdharTransaction).filter(UdharTransaction.id == transaction_id).first()

    if not db_transaction:
        raise HTTPException(status_code=404, detail="Transaction not found.")

    # Check if the transaction is pending the correct party's approval
    is_debit_pending_customer = db_transaction.status == 'pending_customer_approval' and db_transaction.transaction_type == 'DEBIT' and rejector == 'customer'
    is_credit_pending_seller = db_transaction.status == 'pending_seller_approval' and db_transaction.transaction_type == 'CREDIT' and rejector == 'seller'

    if not is_debit_pending_customer and not is_credit_pending_seller:
        raise HTTPException(status_code=400, detail=f"This transaction is not awaiting confirmation from {rejector}.")

    db_transaction.status = "rejected"

    db.commit()
    db.refresh(db_transaction)
    # Trigger notification to the other party
    return db_transaction
