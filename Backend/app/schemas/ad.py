from pydantic import BaseModel
from datetime import datetime

class AdCreate(BaseModel):
    title: str
    subtitle: str
    image_url: str
    redirect_url: str
    pricing_plan_id: int
    duration_seconds: int
    target_pin: str


class AdResponse(BaseModel):
    id: int
    title: str
    subtitle: str
    image_url: str
    redirect_url: str
    priority: int
    duration_seconds: int
    target_pin: str
    click_count: int
    impression_count: int
    start_date: datetime
    end_date: datetime

    class Config:
        orm_mode = True