"""backfill_existing_budget_currency

Revision ID: 2e30efc792c8
Revises: e592651049ff
"""
from typing import Sequence, Union

from alembic import op

revision: str = '2e30efc792c8'
down_revision: Union[str, Sequence[str], None] = 'e592651049ff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('UPDATE mh_monthly_category_budgets AS b SET currency = h.currency FROM mh_households AS h WHERE b.household_id = h.id AND b.currency IS DISTINCT FROM h.currency;')


def downgrade() -> None:
    pass
