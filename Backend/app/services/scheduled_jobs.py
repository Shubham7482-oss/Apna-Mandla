"""
app/services/scheduled_jobs.py

Scheduled background jobs for the financial system.

Jobs defined here:
  1. daily_reconciliation        — runs at 02:00 UTC every day
  2. apply_udhar_interest        — runs at 03:00 UTC every day
  3. mark_udhar_overdue          — runs at 00:05 UTC every day
  4. cleanup_expired_otp         — runs every 30 minutes

Integration:
  These jobs are registered in app/main.py via APScheduler (AsyncIOScheduler).
  Install: pip install apscheduler

  If APScheduler is not available, each function can be triggered manually
  via POST /admin/reconciliation/run (reconciliation) or the relevant
  admin endpoints.

All jobs use their own DB sessions (not request-scoped) and commit
independently. Any single job failure is isolated — other jobs continue.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# JOB 1: Daily Reconciliation
# ─────────────────────────────────────────────────────────────────────────────

def daily_reconciliation() -> None:
    """
    Run a full ledger reconciliation and persist the report.
    Scheduled: 02:00 UTC daily.
    Alert is emitted (log.error) if any issues are found.
    """
    from app.core.database import SessionLocal
    from app.services.reconciliation_service import ReconciliationService

    db = SessionLocal()
    try:
        logger.info("scheduled.reconciliation.start")
        report = ReconciliationService.run(db, triggered_by_id=None, trigger_type="SCHEDULED")
        db.commit()

        if report.is_clean:
            logger.info(
                "scheduled.reconciliation.ok entries=%d duration_ms=%d",
                report.total_entries, report.duration_ms or 0,
            )
        else:
            logger.error(
                "scheduled.reconciliation.FAIL issues=%d — IMMEDIATE REVIEW REQUIRED",
                report.issues_found,
            )
            # TODO: send alert (email/Slack/PagerDuty) here
    except Exception:
        db.rollback()
        logger.exception("scheduled.reconciliation.error")
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# JOB 2: Apply Udhar Interest
# ─────────────────────────────────────────────────────────────────────────────

def apply_udhar_interest() -> None:
    """
    Apply daily interest to all ACTIVE/OVERDUE udhar accounts that
    have a non-zero interest rate.
    Scheduled: 03:00 UTC daily.
    """
    from app.core.database import SessionLocal
    from app.models.udhar_account import UdharAccount, UdharAccountStatus
    from app.services.udhar_service import UdharService

    db = SessionLocal()
    try:
        accounts = (
            db.query(UdharAccount)
            .filter(
                UdharAccount.status.in_([
                    UdharAccountStatus.ACTIVE,
                    UdharAccountStatus.OVERDUE,
                ]),
                UdharAccount.outstanding_balance > 0,
                UdharAccount.interest_rate > 0,
            )
            .all()
        )

        applied = 0
        errors  = 0
        for acc in accounts:
            try:
                txn = UdharService.apply_interest(db, acc.id)
                if txn:
                    applied += 1
            except Exception:
                errors += 1
                logger.exception("scheduled.udhar_interest.error account=%d", acc.id)
                db.rollback()   # rollback this account; continue with others
                continue

        db.commit()
        logger.info(
            "scheduled.udhar_interest.done accounts_checked=%d applied=%d errors=%d",
            len(accounts), applied, errors,
        )
    except Exception:
        db.rollback()
        logger.exception("scheduled.udhar_interest.fatal")
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# JOB 3: Mark Overdue Accounts
# ─────────────────────────────────────────────────────────────────────────────

def mark_udhar_overdue() -> None:
    """
    Flag ACTIVE udhar accounts that have passed their due_date.
    Scheduled: 00:05 UTC daily (just after midnight to catch the new day).
    """
    from app.core.database import SessionLocal
    from app.services.udhar_service import UdharService

    db = SessionLocal()
    try:
        count = UdharService.mark_overdue_accounts(db)
        db.commit()
        if count:
            logger.warning("scheduled.udhar_overdue.marked count=%d", count)
        else:
            logger.info("scheduled.udhar_overdue.none_due")
    except Exception:
        db.rollback()
        logger.exception("scheduled.udhar_overdue.error")
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# JOB 4: Clean Up Expired OTPs
# ─────────────────────────────────────────────────────────────────────────────

def cleanup_expired_otps() -> None:
    """
    Delete OTP rows that have been expired for more than 1 hour.
    Scheduled: every 30 minutes.
    """
    from datetime import timedelta
    from app.core.database import SessionLocal
    from app.models.otp import OTP

    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        deleted = (
            db.query(OTP)
            .filter(OTP.expires_at < cutoff)
            .delete(synchronize_session=False)
        )
        db.commit()
        if deleted:
            logger.info("scheduled.otp_cleanup.deleted count=%d", deleted)
    except Exception:
        db.rollback()
        logger.exception("scheduled.otp_cleanup.error")
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# SCHEDULER SETUP — called once from main.py lifespan
# ─────────────────────────────────────────────────────────────────────────────

def start_scheduler():
    """
    Build and start the APScheduler AsyncIOScheduler.
    Returns the scheduler instance so the caller can shut it down on exit.

    If APScheduler is not installed, logs a warning and returns None.
    The app will still start and run normally — scheduled jobs will simply
    not fire automatically (they can be triggered via admin API endpoints).
    """
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger
    except ImportError:
        logger.warning(
            "APScheduler not installed. Scheduled financial jobs will not run. "
            "Install with: pip install apscheduler"
        )
        return None

    scheduler = AsyncIOScheduler(timezone="UTC")

    # Reconciliation: 02:00 UTC daily
    scheduler.add_job(
        daily_reconciliation,
        CronTrigger(hour=2, minute=0),
        id="daily_reconciliation",
        name="Daily Ledger Reconciliation",
        max_instances=1,
        misfire_grace_time=3600,   # run if missed by up to 1 hour
    )

    # Interest: 03:00 UTC daily
    scheduler.add_job(
        apply_udhar_interest,
        CronTrigger(hour=3, minute=0),
        id="apply_udhar_interest",
        name="Apply Udhar Interest",
        max_instances=1,
        misfire_grace_time=3600,
    )

    # Overdue flagging: 00:05 UTC daily
    scheduler.add_job(
        mark_udhar_overdue,
        CronTrigger(hour=0, minute=5),
        id="mark_udhar_overdue",
        name="Mark Overdue Udhar Accounts",
        max_instances=1,
        misfire_grace_time=600,
    )

    # OTP cleanup: every 30 minutes
    scheduler.add_job(
        cleanup_expired_otps,
        IntervalTrigger(minutes=30),
        id="cleanup_expired_otps",
        name="Clean Expired OTPs",
        max_instances=1,
    )

    scheduler.start()
    logger.info(
        "Scheduler started. Jobs: %s",
        [job.id for job in scheduler.get_jobs()],
    )
    return scheduler
