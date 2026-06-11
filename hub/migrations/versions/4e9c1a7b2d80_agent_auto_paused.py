"""agent auto_paused (per-agent kill switch)

Revision ID: 4e9c1a7b2d80
Revises: 13c7b8eb074b
Create Date: 2026-06-11 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4e9c1a7b2d80"
down_revision: str | None = "13c7b8eb074b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default backfills existing rows: every agent starts NOT paused —
    # the safe default the ORM uses, and the same value a fresh agent gets.
    with op.batch_alter_table("agents", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("auto_paused", sa.Boolean(), nullable=False, server_default=sa.text("0"))
        )


def downgrade() -> None:
    with op.batch_alter_table("agents", schema=None) as batch_op:
        batch_op.drop_column("auto_paused")
