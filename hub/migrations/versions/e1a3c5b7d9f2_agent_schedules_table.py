"""agent_schedules table (scheduled agent tasks)

Revision ID: e1a3c5b7d9f2
Revises: d0f2a4c6e8b1
Create Date: 2026-06-23 11:50:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.db import UTCDateTime

revision: str = "e1a3c5b7d9f2"
down_revision: str | None = "d0f2a4c6e8b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_schedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("agent_slug", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("spec", sa.String(length=120), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("tools", sa.String(length=20), nullable=False, server_default="read"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("next_run_at", UTCDateTime(), nullable=True),
        sa.Column("last_run_at", UTCDateTime(), nullable=True),
        sa.Column("last_status", sa.String(length=16), nullable=True),
        sa.Column("created_by", sa.String(length=60), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_schedules_owner_id", "agent_schedules", ["owner_id"])
    op.create_index("ix_agent_schedules_agent_slug", "agent_schedules", ["agent_slug"])
    op.create_index("ix_agent_schedules_next_run_at", "agent_schedules", ["next_run_at"])
    op.create_index("ix_agent_schedules_due", "agent_schedules", ["enabled", "next_run_at"])


def downgrade() -> None:
    op.drop_table("agent_schedules")
