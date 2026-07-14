from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db

router = APIRouter(prefix="/auth/rider", tags=["Rider Registration"])

@router.post("/register")
def register_rider(db: Session = Depends(get_db)):
    return {"message": "Rider registration logic coming soon"}