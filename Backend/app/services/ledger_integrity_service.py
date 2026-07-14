from hashlib import sha256
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.ledger_entry import LedgerEntry


def verify_full_ledger_integrity(db: Session):

    entries = db.execute(
        select(LedgerEntry)
        .order_by(LedgerEntry.sequence_number.asc())
    ).scalars().all()

    if not entries:
        return {
            "status": "EMPTY_LEDGER",
            "checked_entries": 0,
        }

    previous_hash = "0" * 64
    expected_sequence = 1

    for entry in entries:

        # 1️⃣ Sequence check
        if entry.sequence_number != expected_sequence:
            raise RuntimeError(
                f"Sequence mismatch at ID {entry.id}. "
                f"Expected {expected_sequence}, got {entry.sequence_number}"
            )

        # 2️⃣ Previous hash check
        if entry.previous_hash != previous_hash:
            raise RuntimeError(
                f"Hash chain broken at ID {entry.id}. "
                f"Previous hash mismatch."
            )

        # 3️⃣ Recompute hash
        raw = (
            f"{entry.sequence_number}|"
            f"{entry.wallet_id}|"
            f"{entry.entry_type}|"
            f"{Decimal(entry.amount)}|"
            f"{entry.previous_hash}|"
            f"{entry.created_at.isoformat()}"
        )

        recalculated_hash = sha256(raw.encode()).hexdigest()

        if recalculated_hash != entry.entry_hash:
            raise RuntimeError(
                f"Entry hash mismatch at ID {entry.id}. "
                f"Ledger tampering detected."
            )

        previous_hash = entry.entry_hash
        expected_sequence += 1

    return {
        "status": "OK",
        "checked_entries": len(entries),
    }