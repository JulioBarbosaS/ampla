"""autorespond_runs table (auditable transcript)

Revision ID: 6a1e3c9d4f02
Revises: 5f0d2b8c3e91
Create Date: 2026-06-11 10:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.db import UTCDateTime

revision: str = "6a1e3c9d4f02"
down_revision: str | None = "5f0d2b8c3e91"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "autorespond_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("agent_slug", sa.String(length=60), nullable=False),
        sa.Column("trigger_message_id", sa.Integer(), nullable=True),
        sa.Column("from_sender", sa.String(length=60), nullable=False),
        sa.Column("result", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("reply_preview", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("tools_allowed", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("tools_disallowed", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("guardrails", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("timed_out", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_autorespond_runs_agent", "autorespond_runs", ["agent_slug", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_autorespond_runs_agent", table_name="autorespond_runs")
    op.drop_table("autorespond_runs")
