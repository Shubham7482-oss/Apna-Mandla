"""
app/services/udhar_service.py

UdharService — credit (buy-now-pay-later) operations.

All cash-flow movements go through WalletService/LedgerEntry.
UdharAccount.outstanding_balance tracks the liability (what the borrower owes).

Double-entry accounting per operation:

  USE CREDIT (buy on udhar):
    CR  lender_shop wallet      +amount   (UDHAR_DEBIT)
    ←   customer's liability increases (tracked in UdharAccount.outstanding_balance)

    Note: no DR on the customer's wallet — credit extended means no immediate
    cash from the customer. The shop is paid from the PLATFORM wallet
    (platform bridges the credit), and the customer's obligation is tracked
    in UdharAccount, not the main wallet.

    Actual double entry:
      CR shop_wallet     amount  (UDHAR_DEBIT)
      DR platform_wallet amount  (UDHAR_DEBIT — platform funds the credit)

  REPAYMENT (customer pays cash):
    DR customer_wallet  amount  (UDHAR_REPAYMENT)
    CR platform_wallet  amount  (UDHAR_REPAYMENT — platform receives and settles)
    ←   UdharAccount.outstanding_balance decreases

  INTEREST:
    DR platform_wallet  amount  (UDHAR_INTEREST — interest receivable)
    CR platform_wallet  amount  (zero-sum on platform; recorded for audit only)
    ←   UdharAccount.outstanding_balance increases
    ←   UdharAccount.total_interest_accrued increases
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.udhar_account import UdharAccount, UdharAccountStatus
from app.models.udhar_transaction import UdharTransaction, UdharTxType
from app.services.ledger_service import WalletService, PLATFORM_USER_ID, _round
from app.models.ledger_entry import TransactionPurpose

logger = logging.getLogger(__name__)

# Daily interest rate from annual: rate_daily = rate_annual / 365
_DAYS = Decimal("365")


def _daily_rate(annual_rate: Decimal) -> Decimal:
    return (annual_rate / _DAYS).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


class UdharService:

    # ── Account management ────────────────────────────────────────────────────

    @staticmethod
    def create_account(
        db:              Session,
        borrower_id:     int,
        lender_shop_id:  int,
        credit_limit:    Decimal,
        interest_rate:   Decimal = Decimal("0.00"),
        due_days:        int     = 30,
        idempotency_key: str | None = None,
    ) -> UdharAccount:
        """
        Open a new credit line between a shop and a customer.
        Called by the SHOP (lender) — requires premium subscription.
        """
        credit_limit  = _round(credit_limit)
        interest_rate = interest_rate.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

        max_limit = Decimal(str(settings.UDHAR_MAX_CREDIT_LIMIT))
        max_rate  = Decimal(str(settings.UDHAR_MAX_INTEREST_RATE_PCT))

        if credit_limit <= 0 or credit_limit > max_limit:
            raise HTTPException(400, f"Credit limit must be between ₹1 and ₹{max_limit}.")
        if interest_rate < 0 or interest_rate > max_rate:
            raise HTTPException(400, f"Interest rate must be between 0% and {max_rate}% p.a.")

        # Idempotency check
        if idempotency_key:
            existing = (
                db.query(UdharAccount)
                .filter(UdharAccount.idempotency_key == idempotency_key)
                .first()
            )
            if existing:
                return existing

        # Prevent duplicate accounts
        existing = (
            db.query(UdharAccount)
            .filter(
                UdharAccount.borrower_id == borrower_id,
                UdharAccount.lender_shop_id == lender_shop_id,
            )
            .with_for_update()
            .first()
        )
        if existing:
            raise HTTPException(409, "An udhar account already exists for this borrower-shop pair.")

        account = UdharAccount(
            borrower_id=borrower_id,
            lender_shop_id=lender_shop_id,
            credit_limit=credit_limit,
            interest_rate=interest_rate,
            due_days=due_days,
            outstanding_balance=Decimal("0.00"),
            status=UdharAccountStatus.ACTIVE,
            idempotency_key=idempotency_key,
        )
        db.add(account)
        db.flush()

        logger.info(
            "udhar.account.created id=%d borrower=%d shop=%d limit=%s rate=%s%%",
            account.id, borrower_id, lender_shop_id, credit_limit, interest_rate,
        )
        return account

    # ── Use credit ────────────────────────────────────────────────────────────

    @staticmethod
    def use_credit(
        db:              Session,
        udhar_account_id: int,
        amount:          Decimal,
        shop_user_id:    int,
        order_id:        int | None = None,
        idempotency_key: str | None = None,
    ) -> UdharTransaction:
        """
        Customer uses their credit line to buy goods from the shop.

        Double entry:
          CR shop_wallet      amount  (UDHAR_DEBIT — shop receives value)
          DR platform_wallet  amount  (UDHAR_DEBIT — platform bridges the credit)
        UdharAccount.outstanding_balance += amount
        """
        amount = _round(amount)
        ik = idempotency_key or f"udhar-use-{udhar_account_id}-{order_id or uuid.uuid4().hex[:8]}"

        # Idempotency
        existing_txn = (
            db.query(UdharTransaction)
            .filter(UdharTransaction.idempotency_key == ik)
            .first()
        )
        if existing_txn:
            return existing_txn

        account = (
            db.query(UdharAccount)
            .filter(UdharAccount.id == udhar_account_id)
            .with_for_update()
            .first()
        )
        if not account:
            raise HTTPException(404, "Udhar account not found.")
        if account.status != UdharAccountStatus.ACTIVE:
            raise HTTPException(400, f"Udhar account is {account.status}, cannot use credit.")
        if account.outstanding_balance + amount > account.credit_limit:
            raise HTTPException(
                400,
                f"Credit limit exceeded. Available: ₹{account.available_credit}, Requested: ₹{amount}"
            )
        if account.is_overdue:
            raise HTTPException(400, "Udhar account is overdue. Please repay outstanding balance first.")

        # Wallet double-entry: shop receives money, platform funds it
        cid = str(uuid.uuid4())
        WalletService._credit(
            db=db, user_id=shop_user_id, amount=amount,
            transaction_type=TransactionPurpose.UDHAR_DEBIT,
            correlation_id=cid,
            description=f"Udhar sale — Account #{udhar_account_id}" + (f" Order #{order_id}" if order_id else ""),
            order_id=order_id,
            idempotency_key=f"{ik}-shop-cr",
        )
        WalletService._debit(
            db=db, user_id=PLATFORM_USER_ID, amount=amount,
            transaction_type=TransactionPurpose.UDHAR_DEBIT,
            correlation_id=cid,
            description=f"Platform funds udhar credit — Account #{udhar_account_id}",
            order_id=order_id,
            idempotency_key=f"{ik}-platform-dr",
        )

        # Update udhar account
        account.outstanding_balance = _round(account.outstanding_balance + amount)
        account.last_transaction_at = datetime.now(timezone.utc)
        if not account.due_date:
            account.due_date = datetime.now(timezone.utc) + timedelta(days=account.due_days)

        txn = UdharTransaction(
            udhar_account_id=account.id,
            order_id=order_id,
            transaction_type=UdharTxType.UDHAR_DEBIT.value,
            amount=amount,
            outstanding_after=account.outstanding_balance,
            ledger_correlation_id=cid,
            idempotency_key=ik,
            description=f"Credit used for Order #{order_id}" if order_id else "Credit used",
        )
        db.add(txn)
        db.flush()

        logger.info(
            "udhar.use account=%d amount=%s outstanding=%s cid=%s",
            account.id, amount, account.outstanding_balance, cid,
        )
        return txn

    # ── Repayment ─────────────────────────────────────────────────────────────

    @staticmethod
    def repay(
        db:              Session,
        udhar_account_id: int,
        borrower_user_id: int,
        amount:          Decimal,
        idempotency_key: str | None = None,
    ) -> UdharTransaction:
        """
        Customer repays part or all of their outstanding udhar balance.

        Double entry:
          DR customer_wallet  amount  (UDHAR_REPAYMENT)
          CR platform_wallet  amount  (UDHAR_REPAYMENT — platform receives, settles credit)
        UdharAccount.outstanding_balance -= amount

        Auto-closes account if fully cleared.
        """
        amount = _round(amount)
        ik = idempotency_key or f"udhar-repay-{udhar_account_id}-{uuid.uuid4().hex[:8]}"

        existing_txn = (
            db.query(UdharTransaction)
            .filter(UdharTransaction.idempotency_key == ik)
            .first()
        )
        if existing_txn:
            return existing_txn

        account = (
            db.query(UdharAccount)
            .filter(UdharAccount.id == udhar_account_id)
            .with_for_update()
            .first()
        )
        if not account:
            raise HTTPException(404, "Udhar account not found.")
        if account.status == UdharAccountStatus.CLOSED:
            raise HTTPException(400, "Udhar account is already closed.")
        if amount > account.outstanding_balance:
            raise HTTPException(
                400,
                f"Repayment ₹{amount} exceeds outstanding ₹{account.outstanding_balance}."
            )

        cid = str(uuid.uuid4())
        WalletService._debit(
            db=db, user_id=borrower_user_id, amount=amount,
            transaction_type=TransactionPurpose.UDHAR_REPAYMENT,
            correlation_id=cid,
            description=f"Udhar repayment — Account #{account.id}",
            idempotency_key=f"{ik}-borrower-dr",
        )
        WalletService._credit(
            db=db, user_id=PLATFORM_USER_ID, amount=amount,
            transaction_type=TransactionPurpose.UDHAR_REPAYMENT,
            correlation_id=cid,
            description=f"Udhar repayment received — Account #{account.id}",
            idempotency_key=f"{ik}-platform-cr",
        )

        account.outstanding_balance = _round(account.outstanding_balance - amount)
        account.last_transaction_at = datetime.now(timezone.utc)

        # Auto-close if fully cleared
        if account.outstanding_balance == Decimal("0.00"):
            account.status    = UdharAccountStatus.CLOSED
            account.closed_at = datetime.now(timezone.utc)
            logger.info("udhar.account.closed id=%d — fully repaid", account.id)

        # Clear overdue if repaid enough
        if account.status == UdharAccountStatus.OVERDUE and account.outstanding_balance < account.credit_limit:
            account.status = UdharAccountStatus.ACTIVE

        txn = UdharTransaction(
            udhar_account_id=account.id,
            transaction_type=UdharTxType.UDHAR_REPAYMENT.value,
            amount=amount,
            outstanding_after=account.outstanding_balance,
            ledger_correlation_id=cid,
            idempotency_key=ik,
            description="Repayment",
        )
        db.add(txn)
        db.flush()

        logger.info(
            "udhar.repay account=%d amount=%s remaining=%s cid=%s",
            account.id, amount, account.outstanding_balance, cid,
        )
        return txn

    # ── Interest application ──────────────────────────────────────────────────

    @staticmethod
    def apply_interest(db: Session, account_id: int) -> UdharTransaction | None:
        """
        Apply one day's simple interest to the account's outstanding balance.

        DR platform_wallet  interest_amount  (UDHAR_INTEREST — platform earns)
        CR platform_wallet  interest_amount  (UDHAR_INTEREST — zero-sum, audit only)
        outstanding_balance += interest_amount
        total_interest_accrued += interest_amount

        Returns None if interest rate is 0 or nothing is outstanding.
        Called by the scheduled job in main.py / APScheduler.
        """
        account = (
            db.query(UdharAccount)
            .filter(UdharAccount.id == account_id)
            .with_for_update()
            .first()
        )
        if not account:
            return None
        if account.outstanding_balance <= 0 or account.interest_rate <= 0:
            return None
        if account.status in (UdharAccountStatus.CLOSED, UdharAccountStatus.SUSPENDED):
            return None

        daily_rate    = _daily_rate(account.interest_rate)
        interest_amt  = _round(account.outstanding_balance * daily_rate)
        if interest_amt <= 0:
            return None

        cid = str(uuid.uuid4())
        ik  = f"udhar-interest-{account.id}-{datetime.now(timezone.utc).date().isoformat()}"

        # Check idempotency: don't apply twice on the same day
        existing = (
            db.query(UdharTransaction)
            .filter(UdharTransaction.idempotency_key == ik)
            .first()
        )
        if existing:
            return existing

        # Wallet entries (zero-sum on platform, purely for audit trail)
        WalletService._credit(
            db=db, user_id=PLATFORM_USER_ID, amount=interest_amt,
            transaction_type=TransactionPurpose.UDHAR_INTEREST,
            correlation_id=cid,
            description=f"Interest on Udhar Account #{account.id}",
            idempotency_key=f"{ik}-platform-cr",
        )
        WalletService._debit(
            db=db, user_id=PLATFORM_USER_ID, amount=interest_amt,
            transaction_type=TransactionPurpose.UDHAR_INTEREST,
            correlation_id=cid,
            description=f"Interest receivable — Account #{account.id}",
            idempotency_key=f"{ik}-platform-dr",
        )

        # Update account
        account.outstanding_balance    = _round(account.outstanding_balance + interest_amt)
        account.total_interest_accrued = _round(account.total_interest_accrued + interest_amt)
        account.last_interest_applied_at = datetime.now(timezone.utc)

        txn = UdharTransaction(
            udhar_account_id=account.id,
            transaction_type=UdharTxType.UDHAR_INTEREST.value,
            amount=interest_amt,
            outstanding_after=account.outstanding_balance,
            ledger_correlation_id=cid,
            idempotency_key=ik,
            description=f"Daily interest @ {account.interest_rate}% p.a.",
        )
        db.add(txn)
        db.flush()

        logger.info(
            "udhar.interest account=%d interest=%s outstanding=%s",
            account.id, interest_amt, account.outstanding_balance,
        )
        return txn

    # ── Overdue flagging ──────────────────────────────────────────────────────

    @staticmethod
    def mark_overdue_accounts(db: Session) -> int:
        """
        Called by the nightly scheduler.
        Marks ACTIVE accounts as OVERDUE if past due_date.
        Returns count of accounts updated.
        """
        now = datetime.now(timezone.utc)
        accounts = (
            db.query(UdharAccount)
            .filter(
                UdharAccount.status == UdharAccountStatus.ACTIVE,
                UdharAccount.outstanding_balance > 0,
                UdharAccount.due_date <= now,
            )
            .all()
        )
        for acc in accounts:
            acc.status = UdharAccountStatus.OVERDUE
            logger.warning("udhar.overdue account=%d borrower=%d", acc.id, acc.borrower_id)

        db.flush()
        return len(accounts)


def add_udhar_debit(
    db: Session,
    shop_id: int,
    customer_id: int,
    order_id: int,
    amount: Decimal,
) -> UdharTransaction:
    """
    Wrapper function to support delivery-time Udhar debiting.
    Finds the active UdharAccount between borrower (customer_id) and lender (shop_id),
    then uses UdharService.use_credit.
    """
    from app.models.shop import Shop

    # 1. Find the Shop to get the shop owner's user_id
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if not shop:
        raise HTTPException(404, f"Shop #{shop_id} not found.")

    # 2. Find the active UdharAccount
    account = (
        db.query(UdharAccount)
        .filter(
            UdharAccount.borrower_id == customer_id,
            UdharAccount.lender_shop_id == shop_id,
        )
        .first()
    )
    if not account:
        raise HTTPException(
            404,
            f"No Udhar credit account exists between Customer #{customer_id} and Shop #{shop_id}."
        )

    # 3. Use the credit
    return UdharService.use_credit(
        db=db,
        udhar_account_id=account.id,
        amount=amount,
        shop_user_id=shop.user_id,
        order_id=order_id,
    )
