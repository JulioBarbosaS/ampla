"""agent require_approval (human-in-the-loop auto-respond gate)

Revision ID: b2d4f6a8c0e1
Revises: a1c2e4f6b8d0
Create Date: 2026-06-12 11:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2d4f6a8c0e1"
down_revision: str | None = "a1c2e4f6b8d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default backfills existing rows: approval off by default (the safe
    # default the ORM uses, and what a fresh agent gets).
    with op.batch_alter_table("agents", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("require_approval", sa.Boolean(), nullable=False, server_default=sa.text("0"))
        )


def downgrade() -> None:
    with op.batch_alter_table("agents", schema=None) as batch_op:
        batch_op.drop_column("require_approval")
