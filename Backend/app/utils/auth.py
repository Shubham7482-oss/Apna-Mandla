from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db


# 🔥 Temporary Simple Admin Checker
def get_current_admin(db: Session = Depends(get_db)):
    """
    Temporary admin check.
    Later JWT verification add karenge.
    """
    
    # Abhi ke liye dummy admin allow kar rahe hain
    class DummyAdmin:
        id = 1
        role = "admin"

    return DummyAdmin()