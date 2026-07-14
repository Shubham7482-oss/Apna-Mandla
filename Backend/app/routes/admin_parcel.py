from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.parcel_rate import ParcelRate
from app.schemas.parcel_rate import ParcelRateCreate, ParcelRateUpdate, ParcelRate as ParcelRateSchema
from app.core.auth import require_roles
from app.models.user import User
from typing import List

router = APIRouter(prefix="/admin/parcels", tags=["Admin Parcels"])

@router.post("/rates", response_model=ParcelRateSchema)
def create_parcel_rate(rate: ParcelRateCreate, db: Session = Depends(get_db), admin=Depends(require_roles(["admin"]))):
    db_rate = ParcelRate(**rate.dict())
    db.add(db_rate)
    db.commit()
    db.refresh(db_rate)
    return db_rate

@router.put("/rates/{rate_id}", response_model=ParcelRateSchema)
def update_parcel_rate(rate_id: int, rate: ParcelRateUpdate, db: Session = Depends(get_db), admin=Depends(require_roles(["admin"]))):
    db_rate = db.query(ParcelRate).filter(ParcelRate.id == rate_id).first()
    if not db_rate:
        raise HTTPException(status_code=404, detail="Parcel rate not found")
    for var, value in vars(rate).items():
        setattr(db_rate, var, value) if value else None
    db.commit()
    db.refresh(db_rate)
    return db_rate

@router.get("/rates", response_model=List[ParcelRateSchema])
def get_parcel_rate(db: Session = Depends(get_db), admin=Depends(require_roles(["admin"]))):
    return db.query(ParcelRate).all()
