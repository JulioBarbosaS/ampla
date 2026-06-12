"""notification_subscriptions table (per-thread subscribe/ignore)

Revision ID: a1c2e4f6b8d0
Revises: 9d4b6f3a8e25
Create Date: 2026-06-12 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.db import UTCDateTime

revision: str = "a1c2e4f6b8d0"
down_revision: str | None = "9d4b6f3a8e25"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("subject_key", sa.String(length=120), nullable=False),
        sa.Column("state", sa.String(length=10), nullable=False),
        sa.Column("reason", sa.String(length=24), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notification_subscriptions_user_id", "notification_subscriptions", ["user_id"]
    )
    op.create_index(
        "ix_notif_subs_user_subject",
        "notification_subscriptions",
        ["user_id", "subject_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_notif_subs_user_subject", table_name="notification_subscriptions")
    op.drop_index("ix_notification_subscriptions_user_id", table_name="notification_subscriptions")
    op.drop_table("notification_subscriptions")
