"""
app/services/fraud_service.py

FraudService — pre-transaction fraud checks and post-transaction monitoring.

All checks are non-blocking by default: they log a FraudFlag but do NOT
raise unless the severity is CRITICAL. The WalletService calls
FraudService.pre_check() before posting any debit entry.

Redis-backed counters provide sub-millisecond rate-limit checks when Redis
is available. Falls back to DB queries when Redis is unavailable.
"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.redis_client import redis_available, redis_client
from app.models.fraud_flag import FraudFlag, FraudFlagType
from app.models.ledger_entry import LedgerEntry

logger = logging.getLogger(__name__)

_TWO = Decimal("0.01")


class FraudCheckError(ValueError):
    """Raised when a CRITICAL fraud check fails and the transaction must be blocked."""
    pass


class FraudService:

    # ── Public entry point ────────────────────────────────────────────────────

    @staticmethod
    def pre_check(
        db:        Session,
        user_id:   int,
        wallet_id: int,
        amount:    Decimal,
        ip_address: Optional[str] = None,
    ) -> None:
        """
        Run all fraud checks before a debit entry is written.
        Raises FraudCheckError if the transaction must be blocked.
        Logs FraudFlag rows for anything suspicious.

        Called by WalletService._debit() before modifying any balance.
        """
        amount = amount.quantize(_TWO)

        # 1. Single transaction ceiling
        FraudService._check_single_txn_limit(db, user_id, wallet_id, amount, ip_address)

        # 2. Daily debit cap
        FraudService._check_daily_limit(db, user_id, wallet_id, amount, ip_address)

        # 3. Hourly transaction count (velocity)
        FraudService._check_hourly_velocity(db, user_id, wallet_id, ip_address)

        # 4. Minimum interval between transactions
        FraudService._check_min_interval(db, user_id, wallet_id, ip_address)

        # 5. Amount spike vs historical average
        FraudService._check_velocity_spike(db, user_id, wallet_id, amount, ip_address)

    # ── Individual checks ─────────────────────────────────────────────────────

    @staticmethod
    def _check_single_txn_limit(
        db: Session, user_id: int, wallet_id: int,
        amount: Decimal, ip_address: Optional[str],
    ) -> None:
        limit = Decimal(str(settings.FRAUD_MAX_SINGLE_TXN_AMOUNT))
        if amount > limit:
            _flag(
                db, user_id=user_id, wallet_id=wallet_id,
                flag_type=FraudFlagType.LARGE_AMOUNT,
                severity="HIGH",
                amount=amount,
                ip_address=ip_address,
                description=(
                    f"Single transaction ₹{amount} exceeds limit ₹{limit}."
                ),
            )
            # Block CRITICAL amounts (10x limit)
            if amount > limit * 10:
                raise FraudCheckError(
                    f"Transaction blocked: amount ₹{amount} exceeds absolute limit ₹{limit * 10}."
                )

    @staticmethod
    def _check_daily_limit(
        db: Session, user_id: int, wallet_id: int,
        amount: Decimal, ip_address: Optional[str],
    ) -> None:
        limit = Decimal(str(settings.FRAUD_MAX_DAILY_DEBIT_AMOUNT))
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        daily_sum = (
            db.query(func.coalesce(func.sum(LedgerEntry.amount), Decimal("0")))
            .filter(
                LedgerEntry.wallet_id == wallet_id,
                LedgerEntry.entry_side == "DR",
                LedgerEntry.created_at >= today_start,
            )
            .scalar()
        ) or Decimal("0")

        if Decimal(str(daily_sum)) + amount > limit:
            _flag(
                db, user_id=user_id, wallet_id=wallet_id,
                flag_type=FraudFlagType.DAILY_LIMIT_EXCEEDED,
                severity="HIGH",
                amount=amount,
                ip_address=ip_address,
                description=(
                    f"Daily debit total ₹{daily_sum} + ₹{amount} "
                    f"would exceed daily limit ₹{limit}."
                ),
            )
            raise FraudCheckError(
                f"Daily debit limit of ₹{limit} reached. "
                f"Already debited ₹{daily_sum} today."
            )

    @staticmethod
    def _check_hourly_velocity(
        db: Session, user_id: int, wallet_id: int, ip_address: Optional[str],
    ) -> None:
        limit = settings.FRAUD_MAX_HOURLY_TXN_COUNT
        key   = f"fraud:hourly:{wallet_id}"

        if redis_available():
            try:
                count = redis_client.incr(key)
                if count == 1:
                    redis_client.expire(key, 3600)
                if count > limit:
                    _flag(
                        db, user_id=user_id, wallet_id=wallet_id,
                        flag_type=FraudFlagType.RAPID_TRANSACTIONS,
                        severity="MEDIUM",
                        ip_address=ip_address,
                        description=f"Hourly transaction count {count} exceeds limit {limit}.",
                    )
                    if count > limit * 2:
                        raise FraudCheckError(
                            f"Too many transactions. Limit is {limit}/hour."
                        )
                return
            except FraudCheckError:
                raise
            except Exception as e:
                logger.warning("fraud.hourly_check redis error: %s", e)

        # DB fallback
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        count = (
            db.query(func.count(LedgerEntry.id))
            .filter(
                LedgerEntry.wallet_id == wallet_id,
                LedgerEntry.entry_side == "DR",
                LedgerEntry.created_at >= one_hour_ago,
            )
            .scalar()
        ) or 0
        if count >= limit:
            _flag(
                db, user_id=user_id, wallet_id=wallet_id,
                flag_type=FraudFlagType.RAPID_TRANSACTIONS,
                severity="MEDIUM",
                ip_address=ip_address,
                description=f"Hourly transaction count {count} at/exceeds limit {limit}.",
            )
            if count >= limit * 2:
                raise FraudCheckError(f"Too many transactions. Limit is {limit}/hour.")

    @staticmethod
    def _check_min_interval(
        db: Session, user_id: int, wallet_id: int, ip_address: Optional[str],
    ) -> None:
        min_secs = settings.FRAUD_MIN_TXN_INTERVAL_SECS
        key = f"fraud:last_txn:{wallet_id}"

        if redis_available():
            try:
                import time
                now_ts = time.time()
                last_ts = redis_client.get(key)
                if last_ts and (now_ts - float(last_ts)) < min_secs:
                    elapsed = now_ts - float(last_ts)
                    _flag(
                        db, user_id=user_id, wallet_id=wallet_id,
                        flag_type=FraudFlagType.RAPID_TRANSACTIONS,
                        severity="LOW",
                        ip_address=ip_address,
                        description=f"Transactions {elapsed:.1f}s apart (min {min_secs}s).",
                    )
                redis_client.setex(key, min_secs * 10, str(now_ts))
                return
            except Exception as e:
                logger.warning("fraud.min_interval redis error: %s", e)

        # DB fallback: check last entry timestamp
        last_entry = (
            db.query(LedgerEntry)
            .filter(LedgerEntry.wallet_id == wallet_id, LedgerEntry.entry_side == "DR")
            .order_by(LedgerEntry.created_at.desc())
            .first()
        )
        if last_entry:
            delta = (datetime.now(timezone.utc) - last_entry.created_at).total_seconds()
            if delta < min_secs:
                _flag(
                    db, user_id=user_id, wallet_id=wallet_id,
                    flag_type=FraudFlagType.RAPID_TRANSACTIONS,
                    severity="LOW",
                    ip_address=ip_address,
                    description=f"Transactions {delta:.1f}s apart (min {min_secs}s).",
                )

    @staticmethod
    def _check_velocity_spike(
        db: Session, user_id: int, wallet_id: int,
        amount: Decimal, ip_address: Optional[str],
    ) -> None:
        """Flag if this transaction is >> the 30-day average."""
        spike_factor = Decimal(str(settings.FRAUD_VELOCITY_SPIKE_FACTOR))
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

        avg = (
            db.query(func.avg(LedgerEntry.amount))
            .filter(
                LedgerEntry.wallet_id == wallet_id,
                LedgerEntry.entry_side == "DR",
                LedgerEntry.created_at >= thirty_days_ago,
            )
            .scalar()
        )
        if avg and avg > 0 and amount > Decimal(str(avg)) * spike_factor:
            _flag(
                db, user_id=user_id, wallet_id=wallet_id,
                flag_type=FraudFlagType.VELOCITY_BREACH,
                severity="MEDIUM",
                amount=amount,
                ip_address=ip_address,
                description=(
                    f"Amount ₹{amount} is {amount / Decimal(str(avg)):.1f}x "
                    f"the 30-day average ₹{avg:.2f}."
                ),
            )


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPER
# ─────────────────────────────────────────────────────────────────────────────

def _flag(
    db: Session,
    user_id: int,
    wallet_id: Optional[int],
    flag_type: FraudFlagType,
    severity: str,
    description: str,
    amount: Optional[Decimal] = None,
    ip_address: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> None:
    """Insert a FraudFlag row and emit a structured log line."""
    flag = FraudFlag(
        user_id=user_id,
        wallet_id=wallet_id,
        flag_type=flag_type.value,
        severity=severity,
        amount=float(amount) if amount else None,
        description=description,
        ip_address=ip_address,
        correlation_id=correlation_id,
    )
    db.add(flag)
    db.flush()   # get id without committing

    logger.warning(
        "fraud.flag user=%d wallet=%s type=%s severity=%s amount=%s ip=%s desc=%s",
        user_id, wallet_id, flag_type.value, severity, amount, ip_address, description,
    )
