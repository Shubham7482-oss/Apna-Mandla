"""
app/routes/gateway.py

Payment gateway integration routes.
Router has NO self-prefix; api.py provides /gateway.

Final paths:
  POST /api/v1/gateway/initiate                 — create a payment order
  POST /api/v1/gateway/webhook/{provider}       — receive success webhook
  POST /api/v1/gateway/refund-webhook/{provider}— receive refund webhook
  GET  /api/v1/gateway/payments                 — list my gateway payments
  GET  /api/v1/gateway/payments/{id}            — single payment detail

Security:
  Webhook endpoints verify HMAC-SHA256 signature before processing.
  The signature secret is per-provider and stored in settings.
  Wallet credit only happens AFTER signature verification.
  Idempotency: re-delivery of the same webhook is a safe no-op.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.gateway_payment import GatewayPayment, GatewayProvider
from app.models.user import User
from app.schemas.common import SuccessResponse
from app.services.gateway_service import GatewayService, GatewaySignatureError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Gateway"])


# ─────────────────────────────────────────────────────────────────────────────
# REQUEST SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class InitiateRequest(BaseModel):
    amount:   float
    provider: str = "RAZORPAY"  # RAZORPAY | STRIPE | PHONEPE | PAYTM
    order_id: int | None = None
    currency: str = "INR"


# ─────────────────────────────────────────────────────────────────────────────
# POST /gateway/initiate
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/initiate", status_code=status.HTTP_201_CREATED)
def initiate_payment(
    body:         InitiateRequest,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """
    Create a GatewayPayment row and return the provider's order identifier.
    The client uses gateway_order_id to open the provider's checkout SDK.

    In production: uncomment the real SDK call inside GatewayService.initiate().
    """
    try:
        provider = GatewayProvider(body.provider.upper())
    except ValueError:
        raise HTTPException(400, f"Unknown provider '{body.provider}'. Valid: RAZORPAY, STRIPE, PHONEPE, PAYTM")

    from decimal import Decimal
    amount = Decimal(str(body.amount))
    if amount <= 0:
        raise HTTPException(400, "Amount must be positive.")

    try:
        gp = GatewayService.initiate(
            db=db,
            user_id=current_user.id,
            amount=amount,
            provider=provider,
            order_id=body.order_id,
            currency=body.currency,
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("gateway.initiate.error user=%d", current_user.id)
        raise HTTPException(500, "Failed to initiate payment.")

    return SuccessResponse(
        success=True,
        data={
            "payment_id":       gp.id,
            "gateway_order_id": gp.gateway_order_id,
            "provider":         gp.provider,
            "amount":           float(gp.amount),
            "currency":         gp.currency,
            "status":           gp.status,
        },
        message="Payment initiated. Use gateway_order_id to open checkout.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /gateway/webhook/{provider}
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/webhook/{provider}", status_code=status.HTTP_200_OK)
async def payment_webhook(
    provider:   str,
    request:    Request,
    db:         Session = Depends(get_db),
    x_razorpay_signature: str | None = Header(default=None),
    stripe_signature:     str | None = Header(default=None),
):
    """
    Receive a payment-success webhook from the gateway.

    Signature header names by provider:
      Razorpay: X-Razorpay-Signature
      Stripe:   Stripe-Signature
      Others:   X-Signature

    The webhook secret must be stored in settings (not exposed here).
    """
    try:
        provider_enum = GatewayProvider(provider.upper())
    except ValueError:
        raise HTTPException(400, f"Unknown provider '{provider}'")

    raw_body = await request.body()
    payload: dict[str, Any] = await request.json()

    # Resolve the signature header by provider
    signature = (
        x_razorpay_signature
        or stripe_signature
        or request.headers.get("X-Signature", "")
    )
    if not signature:
        logger.warning("gateway.webhook.missing_signature provider=%s", provider)
        raise HTTPException(400, "Missing webhook signature header.")

    # Resolve the per-provider webhook secret from settings
    from app.core.config import settings as cfg
    webhook_secret_map = {
        GatewayProvider.RAZORPAY: getattr(cfg, "RAZORPAY_WEBHOOK_SECRET", "REPLACE_ME"),
        GatewayProvider.STRIPE:   getattr(cfg, "STRIPE_WEBHOOK_SECRET",   "REPLACE_ME"),
        GatewayProvider.PHONEPE:  getattr(cfg, "PHONEPE_WEBHOOK_SECRET",  "REPLACE_ME"),
        GatewayProvider.PAYTM:    getattr(cfg, "PAYTM_WEBHOOK_SECRET",    "REPLACE_ME"),
        GatewayProvider.MANUAL:   "",
    }
    secret = webhook_secret_map.get(provider_enum, "REPLACE_ME")

    try:
        gp = GatewayService.handle_webhook(
            db=db,
            provider=provider_enum,
            raw_body=raw_body,
            signature=signature,
            webhook_secret=secret,
            payload=payload,
        )
        db.commit()
    except GatewaySignatureError as exc:
        raise HTTPException(400, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception:
        db.rollback()
        logger.exception("gateway.webhook.error provider=%s", provider)
        raise HTTPException(500, "Webhook processing failed.")

    logger.info("gateway.webhook.ok provider=%s gp_id=%d", provider, gp.id)
    # Return 200 — gateway does not need detail
    return {"status": "ok", "payment_id": gp.id}


# ─────────────────────────────────────────────────────────────────────────────
# POST /gateway/refund-webhook/{provider}
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/refund-webhook/{provider}", status_code=status.HTTP_200_OK)
async def refund_webhook(
    provider:   str,
    request:    Request,
    db:         Session = Depends(get_db),
    x_razorpay_signature: str | None = Header(default=None),
    stripe_signature:     str | None = Header(default=None),
):
    """Receive a refund-completed webhook."""
    try:
        provider_enum = GatewayProvider(provider.upper())
    except ValueError:
        raise HTTPException(400, f"Unknown provider '{provider}'")

    raw_body = await request.body()
    payload  = await request.json()
    signature = (
        x_razorpay_signature
        or stripe_signature
        or request.headers.get("X-Signature", "")
    )

    from app.core.config import settings as cfg
    secret_map = {
        GatewayProvider.RAZORPAY: getattr(cfg, "RAZORPAY_WEBHOOK_SECRET", "REPLACE_ME"),
        GatewayProvider.STRIPE:   getattr(cfg, "STRIPE_WEBHOOK_SECRET",   "REPLACE_ME"),
        GatewayProvider.PHONEPE:  getattr(cfg, "PHONEPE_WEBHOOK_SECRET",  "REPLACE_ME"),
        GatewayProvider.PAYTM:    getattr(cfg, "PAYTM_WEBHOOK_SECRET",    "REPLACE_ME"),
        GatewayProvider.MANUAL:   "",
    }

    try:
        gp = GatewayService.handle_refund_webhook(
            db=db,
            provider=provider_enum,
            raw_body=raw_body,
            signature=signature,
            webhook_secret=secret_map.get(provider_enum, "REPLACE_ME"),
            payload=payload,
        )
        db.commit()
    except GatewaySignatureError as exc:
        raise HTTPException(400, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception:
        db.rollback()
        logger.exception("gateway.refund_webhook.error provider=%s", provider)
        raise HTTPException(500, "Refund webhook processing failed.")

    return {"status": "ok", "payment_id": gp.id}


# ─────────────────────────────────────────────────────────────────────────────
# GET /gateway/payments
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/payments")
def list_my_gateway_payments(
    page:         int     = 1,
    page_size:    int     = 20,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    """List gateway payments for the current user."""
    q = (
        db.query(GatewayPayment)
        .filter(GatewayPayment.user_id == current_user.id)
        .order_by(GatewayPayment.created_at.desc())
    )
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()

    return SuccessResponse(
        success=True,
        data={
            "page": page, "page_size": page_size, "total": total,
            "items": [
                {
                    "id":                gp.id,
                    "provider":          gp.provider,
                    "amount":            float(gp.amount),
                    "currency":          gp.currency,
                    "status":            gp.status,
                    "gateway_order_id":  gp.gateway_order_id,
                    "gateway_payment_id":gp.gateway_payment_id,
                    "created_at":        gp.created_at.isoformat(),
                    "completed_at":      gp.completed_at.isoformat() if gp.completed_at else None,
                }
                for gp in items
            ],
        },
        message="Gateway payments fetched.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /gateway/payments/{id}
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/payments/{payment_id}")
def get_gateway_payment(
    payment_id:   int,
    current_user: User    = Depends(get_current_user),
    db:           Session = Depends(get_db),
):
    gp = (
        db.query(GatewayPayment)
        .filter(
            GatewayPayment.id == payment_id,
            GatewayPayment.user_id == current_user.id,   # IDOR guard
        )
        .first()
    )
    if not gp:
        raise HTTPException(404, "Payment not found.")

    return SuccessResponse(
        success=True,
        data={
            "id":                   gp.id,
            "provider":             gp.provider,
            "amount":               float(gp.amount),
            "currency":             gp.currency,
            "status":               gp.status,
            "gateway_order_id":     gp.gateway_order_id,
            "gateway_payment_id":   gp.gateway_payment_id,
            "order_id":             gp.order_id,
            "ledger_correlation_id":gp.ledger_correlation_id,
            "failure_reason":       gp.failure_reason,
            "created_at":           gp.created_at.isoformat(),
            "completed_at":         gp.completed_at.isoformat() if gp.completed_at else None,
            "refunded_at":          gp.refunded_at.isoformat()  if gp.refunded_at  else None,
        },
        message="Payment detail fetched.",
    )
