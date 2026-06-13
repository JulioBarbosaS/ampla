"""agent auto_schedule (availability window / DND)

Revision ID: d4f6a8c0e2b3
Revises: c3e5a7b9d1f2
Create Date: 2026-06-12 13:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4f6a8c0e2b3"
down_revision: str | None = "c3e5a7b9d1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable (NULL = always-on), so existing rows backfill to "no schedule"
    # without a server_default — like the daily-budget columns.
    with op.batch_alter_table("agents", schema=None) as batch_op:
        batch_op.add_column(sa.Column("auto_schedule", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("agents", schema=None) as batch_op:
        batch_op.drop_column("auto_schedule")
