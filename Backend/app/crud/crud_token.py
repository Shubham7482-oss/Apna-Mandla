from app.crud.base import CRUDBase
from app.models.token import Token
from app.schemas.token import TokenCreate, TokenUpdate


class CRUDToken(CRUDBase[Token, TokenCreate, TokenUpdate]):
    pass


token = CRUDToken(Token)
