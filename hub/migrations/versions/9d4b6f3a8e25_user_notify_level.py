"""user notify_level (notification delivery gate)

Revision ID: 9d4b6f3a8e25
Revises: 8c3a5e2f7d14
Create Date: 2026-06-12 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9d4b6f3a8e25"
down_revision: str | None = "8c3a5e2f7d14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NOT NULL with a server_default so existing rows backfill to the safe
    # default ("mentions_and_direct"); the model carries the same value as a
    # Python-side default (the drift guard ignores server_default).
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "notify_level",
                sa.String(length=16),
                nullable=False,
                server_default=sa.text("'mentions_and_direct'"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("notify_level")
