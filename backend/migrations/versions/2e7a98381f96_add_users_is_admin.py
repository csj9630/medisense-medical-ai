"""add users.is_admin

Revision ID: 2e7a98381f96
Revises: 5d7e62474617
Create Date: 2026-08-21 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '2e7a98381f96'
down_revision: Union[str, Sequence[str], None] = '5d7e62474617'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('is_admin', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        schema='app_db',
    )


def downgrade() -> None:
    op.drop_column('users', 'is_admin', schema='app_db')
