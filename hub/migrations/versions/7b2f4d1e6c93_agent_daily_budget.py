"""agent daily auto-respond budget

Revision ID: 7b2f4d1e6c93
Revises: 6a1e3c9d4f02
Create Date: 2026-06-11 11:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7b2f4d1e6c93"
down_revision: str | None = "6a1e3c9d4f02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable (NULL = unlimited), so existing rows backfill to "no budget"
    # without a server_default.
    with op.batch_alter_table("agents", schema=None) as batch_op:
        batch_op.add_column(sa.Column("max_auto_tokens_per_day", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("max_auto_cost_usd_per_day", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("agents", schema=None) as batch_op:
        batch_op.drop_column("max_auto_cost_usd_per_day")
        batch_op.drop_column("max_auto_tokens_per_day")
