"""approvals table (human-in-the-loop auto-reply)

Revision ID: c3e5a7b9d1f2
Revises: b2d4f6a8c0e1
Create Date: 2026-06-12 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.db import UTCDateTime

revision: str = "c3e5a7b9d1f2"
down_revision: str | None = "b2d4f6a8c0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "approvals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("agent_slug", sa.String(length=60), nullable=False),
        sa.Column("trigger_message_id", sa.Integer(), nullable=True),
        sa.Column("to_agent", sa.String(length=60), nullable=False),
        sa.Column("draft_body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("decided_by", sa.Integer(), nullable=True),
        sa.Column("decided_at", UTCDateTime(), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approvals_agent_slug", "approvals", ["agent_slug"])
    op.create_index("ix_approvals_created_at", "approvals", ["created_at"])
    op.create_index("ix_approvals_agent_status", "approvals", ["agent_slug", "status"])


def downgrade() -> None:
    op.drop_index("ix_approvals_agent_status", table_name="approvals")
    op.drop_index("ix_approvals_created_at", table_name="approvals")
    op.drop_index("ix_approvals_agent_slug", table_name="approvals")
    op.drop_table("approvals")
