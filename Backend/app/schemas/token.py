from pydantic import BaseModel, ConfigDict
from typing import Optional


class TokenPayload(BaseModel):
    sub: Optional[int] = None


class TokenBase(BaseModel):
    access_token: str
    token_type: str


class TokenCreate(TokenBase):
    user_id: int


class TokenUpdate(BaseModel):
    is_revoked: Optional[bool] = None


class Token(TokenBase):
    id: int
    user_id: int

    model_config = ConfigDict(from_attributes=True)
