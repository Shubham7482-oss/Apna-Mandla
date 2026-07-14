# app/schemas/rider.py

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class RiderActivateResponse(BaseModel):
    rider_id: int
    work_id: str
    message: str


class RiderDutyUpdate(BaseModel):
    on_duty: bool


class RiderPublicView(BaseModel):
    name: str
    role: str
    active: bool
    job_in_progress: bool
    documents_verified: bool
    police_verified: bool
