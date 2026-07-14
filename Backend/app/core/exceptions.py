from fastapi import HTTPException, status

class ApnaMandlaException(HTTPException):
    def __init__(self, detail: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        super().__init__(status_code=status_code, detail=detail)

class InsufficientBalanceError(ApnaMandlaException):
    def __init__(self):
        super().__init__(detail="Insufficient balance in wallet.")

class RiderNotAvailableError(ApnaMandlaException):
    def __init__(self):
        super().__init__(detail="No riders are currently available in this area.")

class OrderNotFoundError(ApnaMandlaException):
    def __init__(self):
        super().__init__(detail="Order not found.", status_code=status.HTTP_404_NOT_FOUND)