
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List

from app.core.database import get_db
from app.models.parcel import Parcel, ParcelStatus
from app.schemas.parcel import ParcelCreate, Parcel as ParcelSchema
from app.models.user import User
from app.core.auth import get_current_user
from app.services.rate_service import calculate_delivery_fee

router = APIRouter()

@router.post("/", response_model=ParcelSchema)
def create_parcel(parcel: ParcelCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Calculate delivery fee
    rate = calculate_delivery_fee(parcel.distance)
    
    db_parcel = Parcel(**parcel.dict(), sender_id=current_user.id, rate=rate)
    db.add(db_parcel)
    db.commit()
    db.refresh(db_parcel)
    return db_parcel

@router.get("/my-parcels", response_model=List[ParcelSchema])
def get_my_parcels(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.user_type == 'RIDER':
        return db.query(Parcel).filter(Parcel.rider_id == current_user.id).all()
    else:
        return db.query(Parcel).filter(
            or_(Parcel.sender_id == current_user.id, Parcel.recipient_id == current_user.id)
        ).all()

@router.get("/{parcel_id}", response_model=ParcelSchema)
def get_parcel(parcel_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.user_type == 'RIDER':
        db_parcel = db.query(Parcel).filter(Parcel.id == parcel_id, Parcel.rider_id == current_user.id).first()
    else:
        db_parcel = db.query(Parcel).filter(Parcel.id == parcel_id, or_(Parcel.sender_id == current_user.id, Parcel.recipient_id == current_user.id)).first()

    if not db_parcel:
        raise HTTPException(status_code=404, detail="Parcel not found")
    return db_parcel

@router.post("/{parcel_id}/picked-up", response_model=ParcelSchema)
def mark_parcel_as_picked_up(parcel_id: int, db: Session = Depends(get_db)):
    db_parcel = db.query(Parcel).filter(Parcel.id == parcel_id).first()
    if not db_parcel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parcel not found")

    if db_parcel.status != ParcelStatus.ASSIGNED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Parcel with status {db_parcel.status} cannot be marked as picked up.")

    db_parcel.status = ParcelStatus.PICKED_UP
    db.commit()
    db.refresh(db_parcel)
    return db_parcel

@router.post("/{parcel_id}/in-transit", response_model=ParcelSchema)
def mark_parcel_as_in_transit(parcel_id: int, db: Session = Depends(get_db)):
    db_parcel = db.query(Parcel).filter(Parcel.id == parcel_id).first()
    if not db_parcel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parcel not found")

    if db_parcel.status != ParcelStatus.PICKED_UP:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Parcel with status {db_parcel.status} cannot be marked as in transit.")

    db_parcel.status = ParcelStatus.IN_TRANSIT
    db.commit()
    db.refresh(db_parcel)
    return db_parcel

@router.post("/{parcel_id}/delivered", response_model=ParcelSchema)
def mark_parcel_as_delivered(parcel_id: int, db: Session = Depends(get_db)):
    db_parcel = db.query(Parcel).filter(Parcel.id == parcel_id).first()
    if not db_parcel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parcel not found")

    if db_parcel.status != ParcelStatus.IN_TRANSIT:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Parcel with status {db_parcel.status} cannot be marked as delivered.")

    db_parcel.status = ParcelStatus.DELIVERED
    db.commit()
    db.refresh(db_parcel)
    return db_parcel
