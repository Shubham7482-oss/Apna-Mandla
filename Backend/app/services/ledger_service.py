"""
app/services/ledger_service.py

WalletService — the ONLY place that modifies wallet balances.

Changes in this revision:
  - FraudService.pre_check() called before every _debit()
  - session_id propagated from caller context to LedgerEntry
  - LedgerService shim kept for backward compatibility
"""

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy.orm import Session

from app.models.commission import CommissionConfig
from app.models.ledger_entry import EntrySide, LedgerEntry, TransactionPurpose
from app.models.wallet import Wallet

logger = logging.getLogger(__name__)

PLATFORM_USER_ID: int = 1
MIN_WITHDRAWAL: Decimal = Decimal("10.00")
_TWO = Decimal("0.01")


def _round(value: Decimal) -> Decimal:
    return value.quantize(_TWO, rounding=ROUND_HALF_UP)


# ─────────────────────────────────────────────────────────────────────────────
# PRIVATE PRIMITIVES
# ─────────────────────────────────────────────────────────────────────────────

def _get_or_create_wallet(db: Session, user_id: int, *, lock: bool = True) -> Wallet:
    q = db.query(Wallet).filter(Wallet.user_id == user_id)
    if lock:
        q = q.with_for_update()
    wallet = q.first()
    if wallet is None:
        wallet = Wallet(user_id=user_id, balance=Decimal("0.00"))
        db.add(wallet)
        db.flush()
    return wallet


def _next_sequence(db: Session) -> int:
    last = (
        db.query(LedgerEntry)
        .order_by(LedgerEntry.sequence_number.desc())
        .with_for_update()
        .first()
    )
    return (last.sequence_number + 1) if last else 1


def _last_hash(db: Session) -> str:
    last = (
        db.query(LedgerEntry)
        .order_by(LedgerEntry.sequence_number.desc())
        .first()
    )
    return last.entry_hash if last else "GENESIS"


def _write_entry(
    *,
    db:               Session,
    wallet:           Wallet,
    entry_side:       EntrySide,
    transaction_type: TransactionPurpose,
    amount:           Decimal,
    balance_after:    Decimal,
    correlation_id:   str,
    description:      Optional[str]  = None,
    order_id:         Optional[int]  = None,
    withdrawal_id:    Optional[int]  = None,
    udhar_account_id: Optional[int]  = None,
    idempotency_key:  Optional[str]  = None,
    session_id:       Optional[int]  = None,
) -> LedgerEntry:
    now       = datetime.now(timezone.utc)
    seq       = _next_sequence(db)
    prev_hash = _last_hash(db)
    entry_hash = LedgerEntry.compute_hash(
        wallet_id=wallet.id,
        entry_side=entry_side.value,
        amount=amount,
        balance_after=balance_after,
        prev_hash=prev_hash,
        timestamp=now.isoformat(),
        correlation_id=correlation_id,
    )
    entry = LedgerEntry(
        wallet_id=wallet.id,
        entry_side=entry_side.value,
        transaction_type=transaction_type.value,
        amount=amount,
        balance_after=balance_after,
        correlation_id=correlation_id,
        sequence_number=seq,
        previous_hash=prev_hash,
        entry_hash=entry_hash,
        description=description,
        order_id=order_id,
        withdrawal_id=withdrawal_id,
        udhar_account_id=udhar_account_id,
        idempotency_key=idempotency_key,
        session_id=session_id,
        created_at=now,
    )
    db.add(entry)
    db.flush()
    return entry


def _check_idempotency(db: Session, wallet_id: int, idempotency_key: str) -> Optional[LedgerEntry]:
    if not idempotency_key:
        return None
    return (
        db.query(LedgerEntry)
        .filter(
            LedgerEntry.wallet_id == wallet_id,
            LedgerEntry.idempotency_key == idempotency_key,
        )
        .first()
    )


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC — WalletService
# ─────────────────────────────────────────────────────────────────────────────

class WalletService:

    @staticmethod
    def get_or_create(db: Session, user_id: int) -> Wallet:
        return _get_or_create_wallet(db, user_id, lock=False)

    @staticmethod
    def get_balance(db: Session, user_id: int) -> Decimal:
        return _get_or_create_wallet(db, user_id, lock=False).balance

    @staticmethod
    def _credit(
        db:               Session,
        user_id:          int,
        amount:           Decimal,
        transaction_type: TransactionPurpose,
        correlation_id:   str,
        description:      Optional[str] = None,
        order_id:         Optional[int] = None,
        withdrawal_id:    Optional[int] = None,
        udhar_account_id: Optional[int] = None,
        idempotency_key:  Optional[str] = None,
        session_id:       Optional[int] = None,
    ) -> LedgerEntry:
        amount = _round(amount)
        wallet = _get_or_create_wallet(db, user_id, lock=True)

        if idempotency_key:
            existing = _check_idempotency(db, wallet.id, idempotency_key)
            if existing:
                logger.info("ledger.idempotent wallet=%d key=%s", wallet.id, idempotency_key)
                return existing

        if wallet.is_frozen:
            raise ValueError(f"Wallet {wallet.id} is frozen.")

        wallet.balance = _round(wallet.balance + amount)
        return _write_entry(
            db=db, wallet=wallet,
            entry_side=EntrySide.CR,
            transaction_type=transaction_type,
            amount=amount,
            balance_after=wallet.balance,
            correlation_id=correlation_id,
            description=description,
            order_id=order_id,
            withdrawal_id=withdrawal_id,
            udhar_account_id=udhar_account_id,
            idempotency_key=idempotency_key,
            session_id=session_id,
        )

    @staticmethod
    def _debit(
        db:               Session,
        user_id:          int,
        amount:           Decimal,
        transaction_type: TransactionPurpose,
        correlation_id:   str,
        description:      Optional[str] = None,
        order_id:         Optional[int] = None,
        withdrawal_id:    Optional[int] = None,
        udhar_account_id: Optional[int] = None,
        idempotency_key:  Optional[str] = None,
        session_id:       Optional[int] = None,
        ip_address:       Optional[str] = None,
    ) -> LedgerEntry:
        amount = _round(amount)
        wallet = _get_or_create_wallet(db, user_id, lock=True)

        if idempotency_key:
            existing = _check_idempotency(db, wallet.id, idempotency_key)
            if existing:
                logger.info("ledger.idempotent wallet=%d key=%s", wallet.id, idempotency_key)
                return existing

        if wallet.is_frozen:
            raise ValueError(f"Wallet {wallet.id} is frozen.")

        # ── Fraud check (only for non-platform wallets) ───────────────────────
        if user_id != PLATFORM_USER_ID:
            from app.services.fraud_service import FraudService, FraudCheckError
            try:
                FraudService.pre_check(
                    db=db,
                    user_id=user_id,
                    wallet_id=wallet.id,
                    amount=amount,
                    ip_address=ip_address,
                )
            except FraudCheckError as exc:
                logger.warning(
                    "ledger.debit.fraud_block user=%d amount=%s reason=%s",
                    user_id, amount, exc,
                )
                raise ValueError(str(exc)) from exc

        if wallet.balance < amount:
            raise ValueError(
                f"Insufficient balance. Available: ₹{wallet.balance}, Required: ₹{amount}"
            )

        wallet.balance = _round(wallet.balance - amount)
        return _write_entry(
            db=db, wallet=wallet,
            entry_side=EntrySide.DR,
            transaction_type=transaction_type,
            amount=amount,
            balance_after=wallet.balance,
            correlation_id=correlation_id,
            description=description,
            order_id=order_id,
            withdrawal_id=withdrawal_id,
            udhar_account_id=udhar_account_id,
            idempotency_key=idempotency_key,
            session_id=session_id,
        )

    # ── Public double-entry operations ────────────────────────────────────────

    @staticmethod
    def topup(
        db:              Session,
        user_id:         int,
        amount:          Decimal,
        description:     str           = "Wallet top-up",
        idempotency_key: Optional[str] = None,
        session_id:      Optional[int] = None,
    ) -> Wallet:
        cid    = str(uuid.uuid4())
        amount = _round(amount)
        if amount <= 0:
            raise ValueError("Top-up amount must be positive.")
        WalletService._credit(
            db=db, user_id=user_id, amount=amount,
            transaction_type=TransactionPurpose.TOPUP,
            correlation_id=cid, description=description,
            idempotency_key=idempotency_key, session_id=session_id,
        )
        WalletService._debit(
            db=db, user_id=PLATFORM_USER_ID, amount=amount,
            transaction_type=TransactionPurpose.TOPUP,
            correlation_id=cid,
            description=f"Funds disbursed to user #{user_id}: {description}",
            session_id=session_id,
        )
        logger.info("ledger.topup user=%d amount=%s cid=%s", user_id, amount, cid)
        return _get_or_create_wallet(db, user_id, lock=False)

    @staticmethod
    def process_order_payment(
        db:              Session,
        customer_id:     int,
        shop_user_id:    int,
        total_amount:    Decimal,
        order_id:        int,
        idempotency_key: Optional[str] = None,
        session_id:      Optional[int] = None,
        ip_address:      Optional[str] = None,
    ) -> dict:
        total_amount = _round(total_amount)
        cid          = str(uuid.uuid4())
        ik_prefix    = idempotency_key or f"order-{order_id}"

        commission_config = (
            db.query(CommissionConfig)
            .filter(CommissionConfig.is_active == True)  # noqa: E712
            .order_by(CommissionConfig.created_at.desc())
            .first()
        )
        commission_pct = Decimal(str(commission_config.percent)) if commission_config else Decimal("0.00")
        commission_amt = _round(total_amount * commission_pct / Decimal("100"))
        net_amount     = _round(total_amount - commission_amt)

        WalletService._debit(
            db=db, user_id=customer_id, amount=total_amount,
            transaction_type=TransactionPurpose.ORDER_PAYMENT,
            correlation_id=cid,
            description=f"Payment for Order #{order_id}",
            order_id=order_id,
            idempotency_key=f"{ik_prefix}-customer-dr",
            session_id=session_id, ip_address=ip_address,
        )
        if net_amount > 0:
            WalletService._credit(
                db=db, user_id=shop_user_id, amount=net_amount,
                transaction_type=TransactionPurpose.ORDER_PAYMENT,
                correlation_id=cid,
                description=f"Earnings from Order #{order_id} (net of {commission_pct}% commission)",
                order_id=order_id,
                idempotency_key=f"{ik_prefix}-shop-cr",
                session_id=session_id,
            )
        if commission_amt > 0:
            WalletService._credit(
                db=db, user_id=PLATFORM_USER_ID, amount=commission_amt,
                transaction_type=TransactionPurpose.COMMISSION,
                correlation_id=cid,
                description=f"Commission ({commission_pct}%) from Order #{order_id}",
                order_id=order_id,
                idempotency_key=f"{ik_prefix}-platform-commission",
                session_id=session_id,
            )
        logger.info(
            "ledger.order_payment order=%d customer=%d shop=%d total=%s net=%s commission=%s",
            order_id, customer_id, shop_user_id, total_amount, net_amount, commission_amt,
        )
        return {"total": total_amount, "net": net_amount, "commission": commission_amt}

    @staticmethod
    def process_refund(
        db:              Session,
        customer_id:     int,
        shop_user_id:    int,
        total_amount:    Decimal,
        order_id:        int,
        commission_pct:  Decimal       = Decimal("0.00"),
        idempotency_key: Optional[str] = None,
        session_id:      Optional[int] = None,
    ) -> None:
        total_amount   = _round(total_amount)
        commission_amt = _round(total_amount * commission_pct / Decimal("100"))
        net_amount     = _round(total_amount - commission_amt)
        cid            = str(uuid.uuid4())
        ik_prefix      = idempotency_key or f"refund-order-{order_id}"

        if net_amount > 0:
            WalletService._debit(
                db=db, user_id=shop_user_id, amount=net_amount,
                transaction_type=TransactionPurpose.REFUND, correlation_id=cid,
                description=f"Refund reversal for Order #{order_id}",
                order_id=order_id, idempotency_key=f"{ik_prefix}-shop-dr",
                session_id=session_id,
            )
        if commission_amt > 0:
            WalletService._debit(
                db=db, user_id=PLATFORM_USER_ID, amount=commission_amt,
                transaction_type=TransactionPurpose.REFUND, correlation_id=cid,
                description=f"Commission refund for Order #{order_id}",
                order_id=order_id, idempotency_key=f"{ik_prefix}-platform-dr",
                session_id=session_id,
            )
        WalletService._credit(
            db=db, user_id=customer_id, amount=total_amount,
            transaction_type=TransactionPurpose.REFUND, correlation_id=cid,
            description=f"Refund for Order #{order_id}",
            order_id=order_id, idempotency_key=f"{ik_prefix}-customer-cr",
            session_id=session_id,
        )
        logger.info("ledger.refund order=%d amount=%s", order_id, total_amount)

    @staticmethod
    def credit_delivery_fee(
        db:              Session,
        rider_user_id:   int,
        amount:          Decimal,
        order_id:        int,
        idempotency_key: Optional[str] = None,
        session_id:      Optional[int] = None,
    ) -> None:
        amount    = _round(amount)
        cid       = str(uuid.uuid4())
        ik_prefix = idempotency_key or f"delivery-fee-{order_id}"
        WalletService._debit(
            db=db, user_id=PLATFORM_USER_ID, amount=amount,
            transaction_type=TransactionPurpose.DELIVERY_FEE, correlation_id=cid,
            description=f"Delivery fee payout for Order #{order_id}",
            order_id=order_id, idempotency_key=f"{ik_prefix}-platform-dr",
            session_id=session_id,
        )
        WalletService._credit(
            db=db, user_id=rider_user_id, amount=amount,
            transaction_type=TransactionPurpose.DELIVERY_FEE, correlation_id=cid,
            description=f"Delivery fee for Order #{order_id}",
            order_id=order_id, idempotency_key=f"{ik_prefix}-rider-cr",
            session_id=session_id,
        )
        logger.info("ledger.delivery_fee rider=%d order=%d amount=%s", rider_user_id, order_id, amount)

    @staticmethod
    def initiate_withdrawal(
        db:              Session,
        user_id:         int,
        amount:          Decimal,
        withdrawal_id:   int,
        idempotency_key: Optional[str] = None,
        session_id:      Optional[int] = None,
        ip_address:      Optional[str] = None,
    ) -> LedgerEntry:
        amount    = _round(amount)
        min_wd    = Decimal(str(getattr(__import__("app.core.config", fromlist=["settings"]), "settings").MIN_WITHDRAWAL_AMOUNT))
        if amount < min_wd:
            raise ValueError(f"Minimum withdrawal is ₹{min_wd}")
        cid       = str(uuid.uuid4())
        ik_prefix = idempotency_key or f"withdrawal-{withdrawal_id}"
        dr_entry  = WalletService._debit(
            db=db, user_id=user_id, amount=amount,
            transaction_type=TransactionPurpose.WITHDRAWAL, correlation_id=cid,
            description=f"Withdrawal request #{withdrawal_id}",
            withdrawal_id=withdrawal_id, idempotency_key=f"{ik_prefix}-user-dr",
            session_id=session_id, ip_address=ip_address,
        )
        WalletService._credit(
            db=db, user_id=PLATFORM_USER_ID, amount=amount,
            transaction_type=TransactionPurpose.WITHDRAWAL, correlation_id=cid,
            description=f"Withdrawal escrow from user #{user_id}",
            withdrawal_id=withdrawal_id, idempotency_key=f"{ik_prefix}-platform-cr",
            session_id=session_id,
        )
        logger.info("ledger.withdrawal_initiated user=%d amount=%s", user_id, amount)
        return dr_entry

    @staticmethod
    def reverse_withdrawal(
        db:            Session,
        user_id:       int,
        amount:        Decimal,
        withdrawal_id: int,
        session_id:    Optional[int] = None,
    ) -> None:
        amount = _round(amount)
        cid    = str(uuid.uuid4())
        WalletService._debit(
            db=db, user_id=PLATFORM_USER_ID, amount=amount,
            transaction_type=TransactionPurpose.REFUND, correlation_id=cid,
            description=f"Rejected withdrawal #{withdrawal_id} → user #{user_id}",
            withdrawal_id=withdrawal_id, session_id=session_id,
        )
        WalletService._credit(
            db=db, user_id=user_id, amount=amount,
            transaction_type=TransactionPurpose.REFUND, correlation_id=cid,
            description=f"Withdrawal #{withdrawal_id} rejected — returned",
            withdrawal_id=withdrawal_id, session_id=session_id,
        )
        logger.info("ledger.withdrawal_reversed user=%d amount=%s", user_id, amount)

    @staticmethod
    def verify_integrity(db: Session) -> dict:
        """Delegates to ReconciliationService for backward compatibility."""
        from app.services.reconciliation_service import ReconciliationService
        report = ReconciliationService.run(db, trigger_type="INTEGRITY_CHECK")
        return {
            "is_secure":     report.is_clean,
            "total_entries": report.total_entries,
            "issues":        [] if not report.issues_json else __import__("json").loads(report.issues_json),
            "verified_at":   report.created_at.isoformat(),
        }


# ── Backward compatibility shim ───────────────────────────────────────────────

class LedgerService:
    @staticmethod
    def get_or_create_wallet(db: Session, user_id: int) -> Wallet:
        return WalletService.get_or_create(db, user_id)

    @staticmethod
    def process_order_payment(db, customer_id, shop_id, total_amount, order_id):
        WalletService.process_order_payment(
            db=db, customer_id=customer_id, shop_user_id=shop_id,
            total_amount=total_amount, order_id=order_id,
            idempotency_key=f"order-{order_id}-legacy",
        )

    @staticmethod
    def credit_rider_delivery_fee(db, rider_id, amount, order_id):
        WalletService.credit_delivery_fee(db, rider_id, amount, order_id)

    @staticmethod
    def verify_system_integrity(db):
        return WalletService.verify_integrity(db)
