"""
app/services/gateway_service.py

Payment gateway integration hooks.

Design: this service is intentionally PROVIDER-AGNOSTIC. It defines
the contract that any gateway adapter must fulfil. The actual SDK calls
live in provider-specific adapters (e.g. razorpay_adapter.py) that are
NOT implemented here — only the structure and idempotent wallet posting.

Webhook signature verification is the ONLY hard security requirement here.
WalletService.topup() is only called AFTER signature is verified.

Flow:
  1. Client calls POST /payment/initiate  → GatewayService.initiate()
       Creates a GatewayPayment row with status=INITIATED.
       Returns the provider order_id for the client SDK to open a checkout.

  2. Gateway calls POST /payment/webhook  → GatewayService.handle_webhook()
       Verifies signature.
       Updates GatewayPayment.status = SUCCESS.
       Calls WalletService.topup() idempotently (gateway_payment_id as key).

  3. For refunds, gateway calls POST /payment/refund-webhook
       → GatewayService.handle_refund_webhook()
"""

import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.gateway_payment import GatewayPayment, GatewayPaymentStatus, GatewayProvider
from app.services.ledger_service import WalletService

logger = logging.getLogger(__name__)


class GatewaySignatureError(ValueError):
    """Raised when webhook signature verification fails."""
    pass


class GatewayService:

    # ── 1. Payment initiation ─────────────────────────────────────────────────

    @staticmethod
    def initiate(
        db:       Session,
        user_id:  int,
        amount:   Decimal,
        provider: GatewayProvider,
        order_id: int | None = None,
        currency: str = "INR",
    ) -> GatewayPayment:
        """
        Create a GatewayPayment row and return it.
        The caller uses gp.gateway_order_id to open the provider checkout.

        In a real implementation this method calls the provider SDK to
        create a payment order and stores the returned order_id.
        """
        # TODO: call provider SDK here, e.g.
        #   razorpay_order = razorpay_client.order.create({"amount": int(amount*100), ...})
        #   gateway_order_id = razorpay_order["id"]
        gateway_order_id = f"MOCK-{provider.value}-{uuid.uuid4().hex[:12].upper()}"

        gp = GatewayPayment(
            user_id=user_id,
            order_id=order_id,
            amount=amount,
            currency=currency,
            provider=provider.value,
            status=GatewayPaymentStatus.INITIATED.value,
            gateway_order_id=gateway_order_id,
        )
        db.add(gp)
        db.flush()

        logger.info(
            "gateway.initiate user=%d provider=%s amount=%s gw_order=%s",
            user_id, provider.value, amount, gateway_order_id,
        )
        return gp

    # ── 2. Success webhook ────────────────────────────────────────────────────

    @staticmethod
    def handle_webhook(
        db:             Session,
        provider:       GatewayProvider,
        raw_body:       bytes,
        signature:      str,
        webhook_secret: str,
        payload:        dict[str, Any],
    ) -> GatewayPayment:
        """
        Process an inbound payment-success webhook.

        Steps:
          1. Verify HMAC signature (raises GatewaySignatureError on failure).
          2. Find the GatewayPayment row by gateway_payment_id.
          3. If already SUCCESS — return idempotently (no double-credit).
          4. Update status to SUCCESS.
          5. Call WalletService.topup() using gateway_payment_id as key.
          6. Store ledger_correlation_id on the GatewayPayment.
        """
        GatewayService._verify_signature(provider, raw_body, signature, webhook_secret)

        gateway_payment_id = GatewayService._extract_payment_id(provider, payload)
        gateway_order_id   = GatewayService._extract_order_id(provider, payload)
        amount_minor       = GatewayService._extract_amount_minor(provider, payload)
        amount             = Decimal(str(amount_minor)) / 100   # paise → rupees

        # Find existing row
        gp = (
            db.query(GatewayPayment)
            .filter(GatewayPayment.gateway_order_id == gateway_order_id)
            .with_for_update()
            .first()
        )
        if not gp:
            raise ValueError(f"GatewayPayment for order {gateway_order_id} not found.")

        # Idempotency — if already processed, return immediately
        if gp.status == GatewayPaymentStatus.SUCCESS.value:
            logger.info("gateway.webhook.duplicate gw_payment=%s", gateway_payment_id)
            return gp

        if gp.status != GatewayPaymentStatus.INITIATED.value:
            raise ValueError(f"Cannot process webhook for payment in status {gp.status}.")

        # Credit the wallet
        ik = f"gateway-topup-{gateway_payment_id}"
        wallet = WalletService.topup(
            db=db,
            user_id=gp.user_id,
            amount=amount,
            description=f"Payment via {provider.value} [{gateway_payment_id}]",
            idempotency_key=ik,
        )

        # Update GatewayPayment
        gp.status                = GatewayPaymentStatus.SUCCESS.value
        gp.gateway_payment_id    = gateway_payment_id
        gp.gateway_signature     = signature
        gp.webhook_payload       = json.dumps(payload, default=str)
        gp.completed_at          = datetime.now(timezone.utc)
        gp.ledger_correlation_id = ik   # same key used in WalletService

        db.flush()
        logger.info(
            "gateway.webhook.success user=%d provider=%s amount=%s gw_payment=%s",
            gp.user_id, provider.value, amount, gateway_payment_id,
        )
        return gp

    # ── 3. Refund webhook ─────────────────────────────────────────────────────

    @staticmethod
    def handle_refund_webhook(
        db:             Session,
        provider:       GatewayProvider,
        raw_body:       bytes,
        signature:      str,
        webhook_secret: str,
        payload:        dict[str, Any],
    ) -> GatewayPayment:
        """
        Process a refund webhook from the gateway.
        Debits the user wallet (money leaves after the gateway refunds).
        """
        GatewayService._verify_signature(provider, raw_body, signature, webhook_secret)

        gateway_payment_id = GatewayService._extract_payment_id(provider, payload)
        amount_minor       = GatewayService._extract_amount_minor(provider, payload)
        amount             = Decimal(str(amount_minor)) / 100

        gp = (
            db.query(GatewayPayment)
            .filter(GatewayPayment.gateway_payment_id == gateway_payment_id)
            .with_for_update()
            .first()
        )
        if not gp:
            raise ValueError(f"GatewayPayment {gateway_payment_id} not found.")

        if gp.status == GatewayPaymentStatus.REFUNDED.value:
            return gp   # idempotent

        # Debit wallet (money goes back to gateway/bank)
        from app.services.ledger_service import PLATFORM_USER_ID
        WalletService._debit(
            db=db,
            user_id=gp.user_id,
            amount=amount,
            transaction_type=__import__(
                "app.models.ledger_entry", fromlist=["TransactionPurpose"]
            ).TransactionPurpose.REFUND,
            correlation_id=str(uuid.uuid4()),
            description=f"Gateway refund [{provider.value}] {gateway_payment_id}",
            idempotency_key=f"gateway-refund-{gateway_payment_id}",
        )

        gp.status      = GatewayPaymentStatus.REFUNDED.value
        gp.refunded_at = datetime.now(timezone.utc)
        db.flush()

        logger.info(
            "gateway.refund user=%d provider=%s amount=%s gw_payment=%s",
            gp.user_id, provider.value, amount, gateway_payment_id,
        )
        return gp

    # ── Signature helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _verify_signature(
        provider: GatewayProvider, raw_body: bytes, signature: str, secret: str
    ) -> None:
        """
        Constant-time HMAC-SHA256 verification.
        Replace with provider-specific logic when integrating real SDKs.
        """
        expected = hmac.new(
            secret.encode("utf-8"), raw_body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            logger.warning("gateway.signature_fail provider=%s", provider.value)
            raise GatewaySignatureError(
                f"Webhook signature verification failed for provider {provider.value}."
            )

    @staticmethod
    def _extract_payment_id(provider: GatewayProvider, payload: dict) -> str:
        """Extract provider-specific payment ID from webhook payload."""
        if provider == GatewayProvider.RAZORPAY:
            return payload.get("payload", {}).get("payment", {}).get("entity", {}).get("id", "")
        if provider == GatewayProvider.STRIPE:
            return payload.get("data", {}).get("object", {}).get("payment_intent", "")
        return payload.get("payment_id", "")

    @staticmethod
    def _extract_order_id(provider: GatewayProvider, payload: dict) -> str:
        if provider == GatewayProvider.RAZORPAY:
            return payload.get("payload", {}).get("payment", {}).get("entity", {}).get("order_id", "")
        if provider == GatewayProvider.STRIPE:
            return payload.get("data", {}).get("object", {}).get("metadata", {}).get("order_id", "")
        return payload.get("order_id", "")

    @staticmethod
    def _extract_amount_minor(provider: GatewayProvider, payload: dict) -> int:
        """Return amount in smallest currency unit (paise for INR)."""
        if provider == GatewayProvider.RAZORPAY:
            return int(payload.get("payload", {}).get("payment", {}).get("entity", {}).get("amount", 0))
        if provider == GatewayProvider.STRIPE:
            return int(payload.get("data", {}).get("object", {}).get("amount", 0))
        return int(payload.get("amount", 0))
