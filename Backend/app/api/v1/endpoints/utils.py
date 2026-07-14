
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db

router = APIRouter()


@router.get("/test")
def test_endpoint(db: Session = Depends(get_db)) -> dict:
    """
    Test endpoint.
    """
    return {"message": "Test endpoint working"}
