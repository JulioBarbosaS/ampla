"""hub_state table (global kill switch)

Revision ID: 5f0d2b8c3e91
Revises: 4e9c1a7b2d80
Create Date: 2026-06-11 09:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5f0d2b8c3e91"
down_revision: str | None = "4e9c1a7b2d80"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hub_state",
        sa.Column("id", sa.Integer(), nullable=False),
        # server_default 1: a fresh/backfilled row starts with auto-respond ON.
        sa.Column(
            "auto_responder_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("hub_state")
