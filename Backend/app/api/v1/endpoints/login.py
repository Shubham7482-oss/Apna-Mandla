
from datetime import timedelta
from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.core.database import get_db
from app.core import security
from app.core.config import settings
from app.core.security import get_password_hash
from app.utils import (
    generate_password_reset_token,
    send_reset_password_email,
    verify_password_reset_token,
)

router = APIRouter()


@router.post("/login/access-token", response_model=schemas.Token)
def login_access_token(
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends()
) -> any:
    """
    OAuth2 compatible token login, get an access token for future requests.

    - **Revokes old tokens**: When a user logs in, all their previously issued tokens
      are invalidated, ensuring only one active session at a time.
    """
    user = crud.user.authenticate(
        db,
        email=form_data.username,
        password=form_data.password
    )
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    elif not crud.user.is_active(user):
        raise HTTPException(status_code=400, detail="Inactive user")

    # Revoke all existing valid tokens for this user
    crud.token.revoke_all_valid_tokens(db, user_id=user.id)

    # Create new access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    token = security.create_access_token(
        user.id,
        expires_delta=access_token_expires,
    )

    # Save the new token to the database
    crud.token.create_user_token(db, user_id=user.id, token=token["access_token"])

    return {
        "access_token": token["access_token"],
        "token_type": "bearer",
    }
