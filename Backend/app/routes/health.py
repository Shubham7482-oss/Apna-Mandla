# app/routes/health.py

from fastapi import APIRouter
from datetime import datetime

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check():
    """
    Basic health check endpoint.

    Used for:
    - load balancer checks
    - uptime monitoring
    - deployment validation

    Must NOT expose internal system details.
    """
    return {
        "status": "ok",
        "service": "apna-mandla-backend",
        "timestamp": datetime.utcnow().isoformat(),
    }
