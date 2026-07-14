from fastapi import HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from decimal import Decimal, InvalidOperation
import logging

from app.models.rider import Rider
from app.services.ledger_service import LedgerService

# Isse config file se bhi utha sakte ho
# It's better to move this to a configuration file (e.g., .env)
COD_LIMIT = Decimal("2000.00")

def settle_cod(db: Session, rider_id: int, amount: Decimal): # Use Decimal for financial input

    if amount <= Decimal("0.00"):
        raise HTTPException(status_code=400, detail="Settlement amount zero se bada hona chahiye")

    # 🔒 Lock rider row (Atomicity)
    rider = (
        db.query(Rider)
        .filter(Rider.id == rider_id)
        .with_for_update()
        .first()
    )

    if not rider:
        raise HTTPException(status_code=404, detail="Rider nahi mila")

    if rider.cod_liability <= Decimal("0.00"):
        raise HTTPException(status_code=400, detail="Rider par koi purana udhaar (COD liability) nahi hai")

    if amount > rider.cod_liability:
        # Option: Extra amount ko wallet mein daal sakte hain, 
        # par abhi ke liye error hi thik hai.
        raise HTTPException(status_code=400, detail=f"Amount liability (₹{rider.cod_liability}) se zyada hai")

    try:
        # 💰 1. LEDGER ENTRY (Rider → Admin)
        # Note: Ye function ledger table mein entry insert karega
        LedgerService.settle_rider_cod(
            db=db,
            rider_id=rider.id,
            amount=amount
        )

        # 🧾 2. REDUCE LIABILITY
        rider.cod_liability -= amount
        rider.last_cod_settlement_at = datetime.utcnow()

        # 🔓 3. UNBLOCK COD (Logic fix: < COD_LIMIT)
        if rider.cod_liability < COD_LIMIT:
            rider.is_cod_blocked = False

        db.commit() # Dono kaam saath mein save honge
        db.refresh(rider)
        return rider

    except Exception as e:
        db.rollback() # Kuch bhi gadbad hui toh ledger aur liability dono rollback
        # Log the actual error for debugging, but show a generic message to the user.
        logging.error(f"COD Settlement failed for rider {rider_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Settlement process fail ho gaya. Kripya support se sampark karein.")