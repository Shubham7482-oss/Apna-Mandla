"""
app/services/reconciliation_service.py

ReconciliationService — mathematical verification of the entire ledger.

Three checks run in sequence:
  1. Hash chain integrity     — previous_hash linkage unbroken
  2. Double-entry balance     — SUM(CR) == SUM(DR) per correlation_id
  3. Wallet cached balance    — wallet.balance == last LedgerEntry.balance_after
  4. Global balance identity  — total CR across ALL wallets == total DR

Results are persisted as ReconciliationReport rows (never updated, only inserted).
"""

import json
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.ledger_entry import LedgerEntry
from app.models.reconciliation_report import ReconciliationReport
from app.models.wallet import Wallet

logger = logging.getLogger(__name__)


class ReconciliationService:

    @staticmethod
    def run(
        db:              Session,
        triggered_by_id: int | None = None,
        trigger_type:    str        = "MANUAL",
    ) -> ReconciliationReport:
        """
        Run a full ledger reconciliation and persist the result.

        Returns the ReconciliationReport row (already flushed, caller commits).
        """
        start_ms = time.monotonic_ns() // 1_000_000
        issues: list[str] = []

        # ── Load all entries in sequence order ────────────────────────────────
        entries = (
            db.query(LedgerEntry)
            .order_by(LedgerEntry.sequence_number.asc())
            .all()
        )
        total_entries = len(entries)

        # ── 1. Hash chain ─────────────────────────────────────────────────────
        prev_hash = "GENESIS"
        for e in entries:
            if e.previous_hash != prev_hash:
                issues.append(
                    f"CHAIN_BREAK seq={e.sequence_number}: "
                    f"expected={prev_hash[:12]}… got={e.previous_hash[:12]}…"
                )
                # Don't stop — report all breaks
            prev_hash = e.entry_hash

        # ── 2. Double-entry balance per correlation_id ────────────────────────
        corr_rows = (
            db.query(
                LedgerEntry.correlation_id,
                func.sum(
                    case((LedgerEntry.entry_side == "CR", LedgerEntry.amount), else_=0)
                ).label("total_cr"),
                func.sum(
                    case((LedgerEntry.entry_side == "DR", LedgerEntry.amount), else_=0)
                ).label("total_dr"),
            )
            .group_by(LedgerEntry.correlation_id)
            .all()
        )
        correlations_checked = len(corr_rows)

        for row in corr_rows:
            cr = Decimal(str(row.total_cr))
            dr = Decimal(str(row.total_dr))
            if abs(cr - dr) > Decimal("0.01"):
                issues.append(
                    f"DOUBLE_ENTRY_IMBALANCE cid={row.correlation_id}: "
                    f"CR={cr} DR={dr} diff={abs(cr - dr)}"
                )

        # ── 3. Wallet cached balance ──────────────────────────────────────────
        wallets = db.query(Wallet).all()
        wallets_checked = len(wallets)

        for w in wallets:
            last_e = (
                db.query(LedgerEntry)
                .filter(LedgerEntry.wallet_id == w.id)
                .order_by(LedgerEntry.sequence_number.desc())
                .first()
            )
            if last_e and abs(w.balance - last_e.balance_after) > Decimal("0.01"):
                issues.append(
                    f"WALLET_BALANCE_MISMATCH wallet_id={w.id}: "
                    f"cached={w.balance} ledger_last={last_e.balance_after}"
                )

            # Also verify: SUM(CR) - SUM(DR) == balance
            sums = (
                db.query(
                    func.coalesce(
                        func.sum(
                            case((LedgerEntry.entry_side == "CR", LedgerEntry.amount), else_=0)
                        ), 0
                    ).label("cr"),
                    func.coalesce(
                        func.sum(
                            case((LedgerEntry.entry_side == "DR", LedgerEntry.amount), else_=0)
                        ), 0
                    ).label("dr"),
                )
                .filter(LedgerEntry.wallet_id == w.id)
                .first()
            )
            computed = Decimal(str(sums.cr)) - Decimal(str(sums.dr))
            if abs(computed - w.balance) > Decimal("0.01"):
                issues.append(
                    f"WALLET_LEDGER_RECOMPUTE_MISMATCH wallet_id={w.id}: "
                    f"computed={computed} cached={w.balance}"
                )

        # ── 4. Global identity: total CR == total DR ──────────────────────────
        global_sums = (
            db.query(
                func.coalesce(
                    func.sum(case((LedgerEntry.entry_side == "CR", LedgerEntry.amount), else_=0)), 0
                ).label("total_cr"),
                func.coalesce(
                    func.sum(case((LedgerEntry.entry_side == "DR", LedgerEntry.amount), else_=0)), 0
                ).label("total_dr"),
            )
            .first()
        )
        total_cr = Decimal(str(global_sums.total_cr))
        total_dr = Decimal(str(global_sums.total_dr))
        if abs(total_cr - total_dr) > Decimal("0.01"):
            issues.append(
                f"GLOBAL_IMBALANCE: total_CR={total_cr} total_DR={total_dr} "
                f"diff={abs(total_cr - total_dr)}"
            )

        # ── Persist result ────────────────────────────────────────────────────
        duration_ms = (time.monotonic_ns() // 1_000_000) - start_ms

        report = ReconciliationReport(
            triggered_by_id=triggered_by_id,
            trigger_type=trigger_type,
            total_entries=total_entries,
            wallets_checked=wallets_checked,
            correlations_checked=correlations_checked,
            issues_found=len(issues),
            is_clean=len(issues) == 0,
            total_cr_sum=total_cr,
            total_dr_sum=total_dr,
            issues_json=json.dumps(issues) if issues else None,
            duration_ms=duration_ms,
        )
        db.add(report)
        db.flush()

        if issues:
            logger.error(
                "reconciliation.FAILED trigger=%s issues=%d duration_ms=%d",
                trigger_type, len(issues), duration_ms,
            )
            for issue in issues:
                logger.error("reconciliation.issue: %s", issue)
        else:
            logger.info(
                "reconciliation.OK trigger=%s entries=%d wallets=%d duration_ms=%d",
                trigger_type, total_entries, wallets_checked, duration_ms,
            )

        return report

    @staticmethod
    def latest_report(db: Session) -> ReconciliationReport | None:
        return (
            db.query(ReconciliationReport)
            .order_by(ReconciliationReport.created_at.desc())
            .first()
        )
