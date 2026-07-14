"""add session fields: ip_address, user_agent, device_info

Revision ID: 002_add_session_fields
Revises: 9e7a27b3d3a7
Create Date: 2024-01-01 00:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = "002_add_session_fields"
down_revision = "9e7a27b3d3a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # All columns are nullable — existing rows are not affected.
    with op.batch_alter_table("active_sessions") as batch_op:
        batch_op.add_column(
            sa.Column("ip_address", sa.String(45), nullable=True)
        )
        batch_op.add_column(
            sa.Column("user_agent", sa.String(512), nullable=True)
        )
        batch_op.add_column(
            sa.Column("device_info", sa.Text(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("active_sessions") as batch_op:
        batch_op.drop_column("device_info")
        batch_op.drop_column("user_agent")
        batch_op.drop_column("ip_address")
