"""add_account_color_and_notes

Revision ID: 4b1e7c9a2d3f
Revises: d241a8eef1ac
Create Date: 2026-10-11 16:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '4b1e7c9a2d3f'
down_revision: Union[str, Sequence[str], None] = 'd241a8eef1ac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('mh_financial_accounts', sa.Column('color', sa.String(length=7), nullable=True))
    op.add_column('mh_financial_accounts', sa.Column('notes', sa.String(length=500), nullable=True))
    op.create_check_constraint(op.f('ck_mh_financial_accounts_color_hex'), 'mh_financial_accounts', "color IS NULL OR color ~ '^#[0-9a-f]{6}$'")
    op.create_check_constraint(op.f('ck_mh_financial_accounts_notes_length'), 'mh_financial_accounts', 'notes IS NULL OR length(notes) <= 500')


def downgrade() -> None:
    op.drop_constraint(op.f('ck_mh_financial_accounts_notes_length'), 'mh_financial_accounts', type_='check')
    op.drop_constraint(op.f('ck_mh_financial_accounts_color_hex'), 'mh_financial_accounts', type_='check')
    op.drop_column('mh_financial_accounts', 'notes')
    op.drop_column('mh_financial_accounts', 'color')
