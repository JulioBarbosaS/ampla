"""delegations table (agent-to-agent task hand-off)

Revision ID: a7c9e1b3d5f7
Revises: f6a8c0e2b4d5
Create Date: 2026-06-15 11:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.db import UTCDateTime

revision: str = "a7c9e1b3d5f7"
down_revision: str | None = "f6a8c0e2b4d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "delegations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("from_agent", sa.String(length=60), nullable=False),
        sa.Column("to_agent", sa.String(length=60), nullable=False),
        sa.Column("task", sa.String(length=2000), nullable=False),
        sa.Column("root_message_id", sa.Integer(), nullable=True),
        sa.Column("result_message_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_delegations_from_agent", "delegations", ["from_agent"])
    op.create_index("ix_delegations_to_agent", "delegations", ["to_agent"])
    op.create_index("ix_delegations_created_at", "delegations", ["created_at"])
    op.create_index("ix_delegations_from_status", "delegations", ["from_agent", "status"])


def downgrade() -> None:
    op.drop_index("ix_delegations_from_status", table_name="delegations")
    op.drop_index("ix_delegations_created_at", table_name="delegations")
    op.drop_index("ix_delegations_to_agent", table_name="delegations")
    op.drop_index("ix_delegations_from_agent", table_name="delegations")
    op.drop_table("delegations")
