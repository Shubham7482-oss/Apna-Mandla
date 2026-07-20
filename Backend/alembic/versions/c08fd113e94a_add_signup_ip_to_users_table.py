"""add signup_ip, email, phone_verified, and email_verified to users table and make hashed_password nullable

Revision ID: c08fd113e94a
Revises: 2263534f5211
Create Date: 2026-07-20 11:32:08.479545

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c08fd113e94a'
down_revision: Union[str, Sequence[str], None] = '2263534f5211'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('signup_ip', sa.String(length=45), nullable=True))
        batch_op.add_column(sa.Column('email', sa.String(length=255), nullable=True))
        batch_op.create_index(op.f('ix_users_email'), ['email'], unique=True)
        batch_op.add_column(sa.Column('phone_verified', sa.Boolean(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('email_verified', sa.Boolean(), nullable=False, server_default='0'))
        batch_op.alter_column('hashed_password', existing_type=sa.String(length=255), nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column('hashed_password', existing_type=sa.String(length=255), nullable=False)
        batch_op.drop_column('email_verified')
        batch_op.drop_column('phone_verified')
        batch_op.drop_index(op.f('ix_users_email'))
        batch_op.drop_column('email')
        batch_op.drop_column('signup_ip')
