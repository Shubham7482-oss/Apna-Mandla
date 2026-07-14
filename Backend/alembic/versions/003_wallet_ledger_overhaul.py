"""wallet and ledger overhaul: new columns for double-entry, idempotency, balance_after

Revision ID: 003_wallet_ledger_overhaul
Revises: 002_add_session_fields
Create Date: 2024-01-02 00:00:00
"""

from alembic import op
import sqlalchemy as sa

revision      = "003_wallet_ledger_overhaul"
down_revision = "002_add_session_fields"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ── wallets ───────────────────────────────────────────────────────────────
    with op.batch_alter_table("wallets") as batch_op:
        batch_op.add_column(sa.Column("is_frozen", sa.Boolean(), nullable=False, server_default="0"))
        # Widen balance column to Numeric(14,2)
        batch_op.alter_column("balance", type_=sa.Numeric(14, 2), existing_nullable=False)
        # Non-negative constraint
        batch_op.create_check_constraint(
            "ck_wallet_balance_non_negative", "balance >= 0"
        )

    # ── ledger_entries ────────────────────────────────────────────────────────
    with op.batch_alter_table("ledger_entries") as batch_op:
        # New required fields (nullable initially so existing rows don't break)
        batch_op.add_column(sa.Column("entry_side",       sa.String(2),   nullable=True))
        batch_op.add_column(sa.Column("transaction_type", sa.String(20),  nullable=True))
        batch_op.add_column(sa.Column("correlation_id",   sa.String(36),  nullable=True))
        batch_op.add_column(sa.Column("balance_after",    sa.Numeric(14, 2), nullable=True))
        batch_op.add_column(sa.Column("idempotency_key",  sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("withdrawal_id",    sa.Integer(),   nullable=True))

        # Migrate existing entry_type values to entry_side and transaction_type
        # (handled in data migration below)

        # New constraints
        batch_op.create_check_constraint(
            "ck_ledger_entry_side_valid", "entry_side IN ('DR', 'CR')"
        )
        batch_op.create_unique_constraint(
            "uq_ledger_idempotency", ["wallet_id", "idempotency_key"]
        )

    # ── Data migration: populate entry_side from entry_type ──────────────────
    # Existing rows: CREDIT → CR, DEBIT → DR
    op.execute("""
        UPDATE ledger_entries
        SET entry_side = CASE entry_type WHEN 'CREDIT' THEN 'CR' ELSE 'DR' END,
            transaction_type = CASE entry_type WHEN 'CREDIT' THEN 'TOPUP' ELSE 'ORDER_PAYMENT' END,
            correlation_id = COALESCE(correlation_id, 'legacy-' || CAST(id AS VARCHAR)),
            balance_after = COALESCE(balance_after, amount)
        WHERE entry_side IS NULL
    """)

    # ── withdrawal_requests ───────────────────────────────────────────────────
    with op.batch_alter_table("withdrawal_requests") as batch_op:
        batch_op.add_column(sa.Column("idempotency_key",   sa.String(100), nullable=True, unique=True))
        batch_op.add_column(sa.Column("admin_note",        sa.String(500), nullable=True))
        batch_op.add_column(sa.Column("processed_by_id",   sa.Integer(),   nullable=True))
        batch_op.add_column(sa.Column("processed_at",      sa.DateTime(timezone=True), nullable=True))
        # Widen amount column
        batch_op.alter_column("amount", type_=sa.Numeric(14, 2), existing_nullable=False)
        batch_op.create_check_constraint("ck_withdrawal_amount_positive", "amount > 0")


def downgrade() -> None:
    with op.batch_alter_table("withdrawal_requests") as batch_op:
        batch_op.drop_constraint("ck_withdrawal_amount_positive", type_="check")
        batch_op.drop_column("processed_at")
        batch_op.drop_column("processed_by_id")
        batch_op.drop_column("admin_note")
        batch_op.drop_column("idempotency_key")

    with op.batch_alter_table("ledger_entries") as batch_op:
        batch_op.drop_constraint("uq_ledger_idempotency", type_="unique")
        batch_op.drop_constraint("ck_ledger_entry_side_valid", type_="check")
        batch_op.drop_column("withdrawal_id")
        batch_op.drop_column("idempotency_key")
        batch_op.drop_column("balance_after")
        batch_op.drop_column("correlation_id")
        batch_op.drop_column("transaction_type")
        batch_op.drop_column("entry_side")

    with op.batch_alter_table("wallets") as batch_op:
        batch_op.drop_constraint("ck_wallet_balance_non_negative", type_="check")
        batch_op.drop_column("is_frozen")
