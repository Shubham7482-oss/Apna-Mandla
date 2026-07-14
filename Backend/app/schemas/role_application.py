from pydantic import BaseModel, ConfigDict
from typing import Optional, Any

class RoleApplicationCreate(BaseModel):
    details: Optional[dict] = None

class RoleApplicationUpdate(BaseModel):
    status: str

class RoleApplicationOut(BaseModel):
    id: int
    user_id: int
    requested_role: str
    status: str
    details: Optional[Any]
    user_name: Optional[str] = None # To show in admin panel

    model_config = ConfigDict(from_attributes=True)
