"""
fintech extension: ledger immutability trigger, udhar overhaul, new tables

Revision ID: 004_fintech_extension
Revises: 003_wallet_ledger_overhaul
Create Date: 2024-01-03
"""

from alembic import op
import sqlalchemy as sa

revision      = "004_fintech_extension"
down_revision = "003_wallet_ledger_overhaul"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ── ledger_entries: new audit columns ─────────────────────────────────────
    with op.batch_alter_table("ledger_entries") as batch_op:
        batch_op.add_column(sa.Column("session_id",        sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("udhar_account_id",  sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_ledger_session",       "ledger_entries", "active_sessions",   ["session_id"],       ["id"],       ondelete="SET NULL")
        batch_op.create_foreign_key("fk_ledger_udhar_account", "ledger_entries", "udhar_accounts",    ["udhar_account_id"], ["id"],       ondelete="SET NULL")

    # ── udhar_accounts: full overhaul ─────────────────────────────────────────
    with op.batch_alter_table("udhar_accounts") as batch_op:
        # Rename user_id → borrower_id
        batch_op.alter_column("user_id", new_column_name="borrower_id")
        # Rename shop_id → lender_shop_id (shops.id)
        batch_op.alter_column("shop_id", new_column_name="lender_shop_id")
        # Rename balance → outstanding_balance
        batch_op.alter_column("balance", new_column_name="outstanding_balance")
        # New columns
        batch_op.add_column(sa.Column("interest_rate",           sa.Numeric(6, 4),           nullable=False, server_default="0.0000"))
        batch_op.add_column(sa.Column("due_days",                sa.Integer(),               nullable=False, server_default="30"))
        batch_op.add_column(sa.Column("due_date",                sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("status",                  sa.String(20),              nullable=False, server_default="ACTIVE"))
        batch_op.add_column(sa.Column("last_interest_applied_at",sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("total_interest_accrued",  sa.Numeric(14, 2),          nullable=False, server_default="0.00"))
        batch_op.add_column(sa.Column("last_transaction_at",     sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("closed_at",               sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("idempotency_key",         sa.String(100),             nullable=True))
        batch_op.create_check_constraint("ck_udhar_credit_limit_pos",   "credit_limit > 0")
        batch_op.create_check_constraint("ck_udhar_outstanding_nn",     "outstanding_balance >= 0")
        batch_op.create_unique_constraint("uq_udhar_borrower_shop",     ["borrower_id", "lender_shop_id"])

    # ── udhar_transactions: add new audit columns ─────────────────────────────
    with op.batch_alter_table("udhar_transactions") as batch_op:
        batch_op.add_column(sa.Column("outstanding_after",      sa.Numeric(14, 2), nullable=True))
        batch_op.add_column(sa.Column("ledger_correlation_id",  sa.String(36),     nullable=True))
        batch_op.add_column(sa.Column("idempotency_key",        sa.String(100),    nullable=True, unique=True))
        # Backfill outstanding_after (approximate — use amount as proxy for existing rows)
        batch_op.create_check_constraint("ck_udhar_txn_amount_pos",      "amount > 0")

    op.execute("UPDATE udhar_transactions SET outstanding_after = amount WHERE outstanding_after IS NULL")

    # ── reconciliation_reports table ──────────────────────────────────────────
    op.create_table(
        "reconciliation_reports",
        sa.Column("id",                    sa.Integer(),              primary_key=True),
        sa.Column("triggered_by_id",       sa.Integer(),              sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("trigger_type",          sa.String(20),             nullable=False),
        sa.Column("total_entries",         sa.Integer(),              nullable=False, server_default="0"),
        sa.Column("wallets_checked",       sa.Integer(),              nullable=False, server_default="0"),
        sa.Column("correlations_checked",  sa.Integer(),              nullable=False, server_default="0"),
        sa.Column("issues_found",          sa.Integer(),              nullable=False, server_default="0"),
        sa.Column("is_clean",              sa.Boolean(),              nullable=False, server_default="1"),
        sa.Column("total_cr_sum",          sa.Numeric(18, 2),         nullable=False, server_default="0"),
        sa.Column("total_dr_sum",          sa.Numeric(18, 2),         nullable=False, server_default="0"),
        sa.Column("issues_json",           sa.Text(),                 nullable=True),
        sa.Column("duration_ms",           sa.Integer(),              nullable=True),
        sa.Column("created_at",            sa.DateTime(timezone=True),nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_reconciliation_created", "reconciliation_reports", ["created_at"])

    # ── fraud_flags table ─────────────────────────────────────────────────────
    op.create_table(
        "fraud_flags",
        sa.Column("id",              sa.Integer(),              primary_key=True),
        sa.Column("user_id",         sa.Integer(),              sa.ForeignKey("users.id",   ondelete="CASCADE"),   nullable=False),
        sa.Column("wallet_id",       sa.Integer(),              sa.ForeignKey("wallets.id", ondelete="SET NULL"),  nullable=True),
        sa.Column("flag_type",       sa.String(30),             nullable=False),
        sa.Column("severity",        sa.String(10),             nullable=False),
        sa.Column("amount",          sa.Numeric(14, 2),         nullable=True),
        sa.Column("description",     sa.Text(),                 nullable=False),
        sa.Column("is_resolved",     sa.Boolean(),              nullable=False, server_default="0"),
        sa.Column("resolved_by_id",  sa.Integer(),              sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolved_at",     sa.DateTime(timezone=True),nullable=True),
        sa.Column("resolution_note", sa.String(500),            nullable=True),
        sa.Column("ip_address",      sa.String(45),             nullable=True),
        sa.Column("correlation_id",  sa.String(36),             nullable=True),
        sa.Column("created_at",      sa.DateTime(timezone=True),nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_fraud_user",       "fraud_flags", ["user_id"])
    op.create_index("ix_fraud_resolved",   "fraud_flags", ["is_resolved"])
    op.create_index("ix_fraud_created",    "fraud_flags", ["created_at"])

    # ── gateway_payments table ────────────────────────────────────────────────
    op.create_table(
        "gateway_payments",
        sa.Column("id",                     sa.Integer(),              primary_key=True),
        sa.Column("user_id",                sa.Integer(),              sa.ForeignKey("users.id",   ondelete="RESTRICT"), nullable=False),
        sa.Column("order_id",               sa.Integer(),              sa.ForeignKey("orders.id",  ondelete="SET NULL"),  nullable=True),
        sa.Column("amount",                 sa.Numeric(14, 2),         nullable=False),
        sa.Column("currency",               sa.String(3),              nullable=False, server_default="INR"),
        sa.Column("provider",               sa.String(20),             nullable=False),
        sa.Column("status",                 sa.String(20),             nullable=False, server_default="INITIATED"),
        sa.Column("gateway_order_id",       sa.String(100),            nullable=True,  unique=True),
        sa.Column("gateway_payment_id",     sa.String(100),            nullable=True,  unique=True),
        sa.Column("gateway_signature",      sa.String(256),            nullable=True),
        sa.Column("failure_reason",         sa.String(500),            nullable=True),
        sa.Column("webhook_payload",        sa.Text(),                 nullable=True),
        sa.Column("ledger_correlation_id",  sa.String(36),             nullable=True),
        sa.Column("created_at",             sa.DateTime(timezone=True),nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at",           sa.DateTime(timezone=True),nullable=True),
        sa.Column("refunded_at",            sa.DateTime(timezone=True),nullable=True),
    )
    op.create_index("ix_gw_user",    "gateway_payments", ["user_id"])
    op.create_index("ix_gw_status",  "gateway_payments", ["status"])
    op.create_index("ix_gw_created", "gateway_payments", ["created_at"])

    # ── DB-level immutability trigger (PostgreSQL) ────────────────────────────
    # SQLite does not support UPDATE/DELETE rules but does support triggers.
    # The ORM events in ledger_entry.py provide protection for both engines.
    # This trigger adds a DB-level guardrail for direct psql/SQLite access.
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_ledger_no_update
        BEFORE UPDATE ON ledger_entries
        BEGIN
            SELECT RAISE(ABORT, 'ledger_entries is append-only. No UPDATE allowed.');
        END
    """)
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_ledger_no_delete
        BEFORE DELETE ON ledger_entries
        BEGIN
            SELECT RAISE(ABORT, 'ledger_entries is append-only. No DELETE allowed.');
        END
    """)
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_udhar_txn_no_update
        BEFORE UPDATE ON udhar_transactions
        BEGIN
            SELECT RAISE(ABORT, 'udhar_transactions is append-only. No UPDATE allowed.');
        END
    """)


def downgrade() -> None:
    # Drop triggers
    op.execute("DROP TRIGGER IF EXISTS trg_ledger_no_update")
    op.execute("DROP TRIGGER IF EXISTS trg_ledger_no_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_udhar_txn_no_update")

    op.drop_table("gateway_payments")
    op.drop_table("fraud_flags")
    op.drop_table("reconciliation_reports")

    with op.batch_alter_table("udhar_transactions") as batch_op:
        batch_op.drop_column("idempotency_key")
        batch_op.drop_column("ledger_correlation_id")
        batch_op.drop_column("outstanding_after")

    with op.batch_alter_table("udhar_accounts") as batch_op:
        batch_op.drop_column("idempotency_key")
        batch_op.drop_column("closed_at")
        batch_op.drop_column("last_transaction_at")
        batch_op.drop_column("total_interest_accrued")
        batch_op.drop_column("last_interest_applied_at")
        batch_op.drop_column("status")
        batch_op.drop_column("due_date")
        batch_op.drop_column("due_days")
        batch_op.drop_column("interest_rate")
        batch_op.alter_column("outstanding_balance", new_column_name="balance")
        batch_op.alter_column("lender_shop_id", new_column_name="shop_id")
        batch_op.alter_column("borrower_id", new_column_name="user_id")

    with op.batch_alter_table("ledger_entries") as batch_op:
        batch_op.drop_column("udhar_account_id")
        batch_op.drop_column("session_id")
