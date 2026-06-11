"""notifications table (user inbox)

Revision ID: 8c3a5e2f7d14
Revises: 7b2f4d1e6c93
Create Date: 2026-06-11 12:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.db import UTCDateTime

revision: str = "8c3a5e2f7d14"
down_revision: str | None = "7b2f4d1e6c93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("subject_type", sa.String(length=16), nullable=False),
        sa.Column("subject_key", sa.String(length=120), nullable=False),
        sa.Column("agent_slug", sa.String(length=60), nullable=True),
        sa.Column("reason", sa.String(length=24), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("link", sa.String(length=255), nullable=False, server_default=sa.text("''")),
        sa.Column("actor", sa.String(length=120), nullable=False, server_default=sa.text("''")),
        sa.Column("unread", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("status", sa.String(length=8), nullable=False, server_default=sa.text("'inbox'")),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.Column("last_read_at", UTCDateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])
    op.create_index("ix_notifications_updated_at", "notifications", ["updated_at"])
    op.create_index("ix_notifications_inbox", "notifications", ["user_id", "status", "updated_at"])
    op.create_index("ix_notifications_subject", "notifications", ["user_id", "subject_key"])


def downgrade() -> None:
    op.drop_index("ix_notifications_subject", table_name="notifications")
    op.drop_index("ix_notifications_inbox", table_name="notifications")
    op.drop_index("ix_notifications_updated_at", table_name="notifications")
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")
