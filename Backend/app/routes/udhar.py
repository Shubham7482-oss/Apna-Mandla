"""
app/routes/udhar.py

Udhar (credit system) API.
Prefix provided by api.py (/udhar); router has NO self-prefix.

Final paths:
  GET    /api/v1/udhar/accounts          — list my accounts (borrower view)
  GET    /api/v1/udhar/{id}              — account detail + transaction history
  POST   /api/v1/udhar/create            — shop opens a credit line for a customer
  POST   /api/v1/udhar/use               — customer uses credit (buy on udhar)
  POST   /api/v1/udhar/repay             — customer repays outstanding balance
"""

import logging
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.feature_guard import is_premium
from app.models.shop import Shop
from app.models.udhar_account import UdharAccount, UdharAccountStatus
from app.models.udhar_transaction import UdharTransaction
from app.models.user import User
from app.schemas.common import SuccessResponse
from app.services.udhar_service import UdharService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Udhar"])


# ─────────────────────────────────────────────────────────────────────────────
# REQUEST SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class CreateUdharRequest(BaseModel):
    borrower_id:     int
    credit_limit:    Decimal = Field(..., gt=0)
    interest_rate:   Decimal = Field(Decimal("0.00"), ge=0, description="Annual % e.g. 12.00")
    due_days:        int     = Field(30, ge=1, le=365)
    idempotency_key: Optional[str] = Field(None, max_length=100)

    @field_validator("credit_limit", "interest_rate", mode="before")
    @classmethod
    def coerce_decimal(cls, v):
        return Decimal(str(v))


class UseUdharRequest(BaseModel):
    udhar_account_id: int
    amount:           Decimal = Field(..., gt=0)
    order_id:         Optional[int] = None
    idempotency_key:  Optional[str] = Field(None, max_length=100)

    @field_validator("amount", mode="before")
    @classmethod
    def coerce_decimal(cls, v):
        return Decimal(str(v))


class RepayUdharRequest(BaseModel):
    udhar_account_id: int
    amount:           Decimal = Field(..., gt=0)
    idempotency_key:  Optional[str] = Field(None, max_length=100)

    @field_validator("amount", mode="before")
    @classmethod
    def coerce_decimal(cls, v):
        return Decimal(str(v))


# ─────────────────────────────────────────────────────────────────────────────
# GET /udhar/accounts  — list my udhar accounts (borrower)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/accounts")
def list_my_accounts(
    status_filter: Optional[str]  = Query(None, alias="status"),
    page:          int             = Query(1, ge=1),
    page_size:     int             = Query(20, ge=1, le=100),
    current_user:  User           = Depends(get_current_user),
    db:            Session        = Depends(get_db),
):
    """Customer sees all their active udhar credit lines."""
    q = db.query(UdharAccount).filter(UdharAccount.borrower_id == current_user.id)
    if status_filter:
        q = q.filter(UdharAccount.status == status_filter.upper())

    total    = q.count()
    accounts = q.order_by(UdharAccount.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return SuccessResponse(
        success=True,
        data={
            "page": page, "page_size": page_size, "total": total,
            "items": [
                {
                    "id":                  a.id,
                    "lender_shop_id":      a.lender_shop_id,
                    "credit_limit":        float(a.credit_limit),
                    "outstanding_balance": float(a.outstanding_balance),
                    "available_credit":    float(a.available_credit),
                    "interest_rate":       float(a.interest_rate),
                    "due_days":            a.due_days,
                    "due_date":            a.due_date.isoformat() if a.due_date else None,
                    "status":              a.status,
                    "is_overdue":          a.is_overdue,
                }
                for a in accounts
            ],
        },
        message="Udhar accounts fetched.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /udhar/{id}  — account detail
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{account_id}")
def get_account_detail(
    account_id:   int,
    page:         int     = Query(1, ge=1),
    page_size:    int     = Query(20, ge=1, le=100),
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    Full account detail with paginated transaction history.
    Accessible by borrower OR the shop's owner.
    """
    account = db.query(UdharAccount).filter(UdharAccount.id == account_id).first()
    if not account:
        raise HTTPException(404, "Udhar account not found.")

    # Access control: borrower OR shop owner
    shop = db.query(Shop).filter(Shop.id == account.lender_shop_id).first()
    is_borrower   = current_user.id == account.borrower_id
    is_shop_owner = shop and shop.user_id == current_user.id
    if not (is_borrower or is_shop_owner):
        raise HTTPException(403, "Access denied.")

    q = (
        db.query(UdharTransaction)
        .filter(UdharTransaction.udhar_account_id == account.id)
        .order_by(UdharTransaction.id.desc())
    )
    total    = q.count()
    txns     = q.offset((page - 1) * page_size).limit(page_size).all()

    return SuccessResponse(
        success=True,
        data={
            "id":                  account.id,
            "borrower_id":         account.borrower_id,
            "lender_shop_id":      account.lender_shop_id,
            "credit_limit":        float(account.credit_limit),
            "outstanding_balance": float(account.outstanding_balance),
            "available_credit":    float(account.available_credit),
            "interest_rate":       float(account.interest_rate),
            "due_days":            account.due_days,
            "due_date":            account.due_date.isoformat() if account.due_date else None,
            "status":              account.status,
            "total_interest_accrued": float(account.total_interest_accrued),
            "created_at":          account.created_at.isoformat(),
            "transactions": {
                "page": page, "page_size": page_size, "total": total,
                "items": [
                    {
                        "id":               t.id,
                        "type":             t.transaction_type,
                        "amount":           float(t.amount),
                        "outstanding_after":float(t.outstanding_after),
                        "description":      t.description,
                        "order_id":         t.order_id,
                        "created_at":       t.created_at.isoformat(),
                    }
                    for t in txns
                ],
            },
        },
        message="Account detail fetched.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /udhar/create  — shop opens a credit line
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/create", status_code=status.HTTP_201_CREATED)
def create_account(
    body:         CreateUdharRequest,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    Shop (lender) opens a new udhar credit line for a customer.
    Requires premium subscription.
    """
    shop = (
        db.query(Shop)
        .filter(Shop.user_id == current_user.id, Shop.is_archived == False)  # noqa: E712
        .first()
    )
    if not shop:
        raise HTTPException(403, "Not a shop owner.")
    if not is_premium(shop):
        raise HTTPException(403, "Udhar feature requires a premium subscription.")

    try:
        account = UdharService.create_account(
            db=db,
            borrower_id=body.borrower_id,
            lender_shop_id=shop.id,
            credit_limit=body.credit_limit,
            interest_rate=body.interest_rate,
            due_days=body.due_days,
            idempotency_key=body.idempotency_key,
        )
        db.commit()
        logger.info("udhar.create account=%d shop=%d borrower=%d", account.id, shop.id, body.borrower_id)
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.exception("udhar.create.error shop=%d", shop.id)
        raise HTTPException(500, "Failed to create udhar account.")

    return SuccessResponse(
        success=True,
        data={
            "account_id":    account.id,
            "credit_limit":  float(account.credit_limit),
            "interest_rate": float(account.interest_rate),
            "due_days":      account.due_days,
            "status":        account.status,
        },
        message="Udhar account created.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /udhar/use  — customer uses credit
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/use", status_code=status.HTTP_201_CREATED)
def use_credit(
    body:         UseUdharRequest,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    Customer uses their credit line to pay for goods.
    Shop wallet is credited. Customer's outstanding balance increases.
    """
    # Verify account belongs to this user
    account = db.query(UdharAccount).filter(UdharAccount.id == body.udhar_account_id).first()
    if not account or account.borrower_id != current_user.id:
        raise HTTPException(404, "Udhar account not found or not yours.")

    shop = db.query(Shop).filter(Shop.id == account.lender_shop_id).first()
    if not shop:
        raise HTTPException(404, "Lender shop not found.")

    try:
        txn = UdharService.use_credit(
            db=db,
            udhar_account_id=body.udhar_account_id,
            amount=body.amount,
            shop_user_id=shop.user_id,
            order_id=body.order_id,
            idempotency_key=body.idempotency_key,
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))
    except Exception:
        db.rollback()
        logger.exception("udhar.use.error account=%d", body.udhar_account_id)
        raise HTTPException(500, "Failed to process credit.")

    return SuccessResponse(
        success=True,
        data={
            "transaction_id":   txn.id,
            "amount":           float(txn.amount),
            "outstanding_after":float(txn.outstanding_after),
        },
        message=f"₹{body.amount} credit used.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /udhar/repay  — customer repays
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/repay", status_code=status.HTTP_200_OK)
def repay(
    body:         RepayUdharRequest,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    Customer repays their udhar balance.
    Debits customer wallet. Decreases outstanding balance.
    Auto-closes account if fully cleared.
    """
    account = db.query(UdharAccount).filter(UdharAccount.id == body.udhar_account_id).first()
    if not account or account.borrower_id != current_user.id:
        raise HTTPException(404, "Udhar account not found or not yours.")

    try:
        txn = UdharService.repay(
            db=db,
            udhar_account_id=body.udhar_account_id,
            borrower_user_id=current_user.id,
            amount=body.amount,
            idempotency_key=body.idempotency_key,
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))
    except Exception:
        db.rollback()
        logger.exception("udhar.repay.error account=%d", body.udhar_account_id)
        raise HTTPException(500, "Repayment failed.")

    # Refresh account to get latest status
    db.refresh(account)

    return SuccessResponse(
        success=True,
        data={
            "transaction_id":   txn.id,
            "amount_paid":      float(txn.amount),
            "outstanding_after":float(txn.outstanding_after),
            "account_status":   account.status,
        },
        message=f"₹{body.amount} repayment recorded."
            + (" Account closed — fully repaid!" if account.status == UdharAccountStatus.CLOSED else ""),
    )
