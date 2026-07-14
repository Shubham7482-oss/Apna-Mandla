from pydantic import BaseModel, EmailStr
from typing import Optional

class AdminCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

class AdminResponse(BaseModel):
    id: int
    username: str
    email: EmailStr

    class Config:
        from_attributes = True