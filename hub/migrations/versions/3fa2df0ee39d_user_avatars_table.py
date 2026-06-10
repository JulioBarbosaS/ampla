"""user avatars table

Revision ID: 3fa2df0ee39d
Revises: f7d5aeb53fc5
Create Date: 2026-06-10 12:01:46.991156
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.db import UTCDateTime

revision: str = "3fa2df0ee39d"
down_revision: str | None = "f7d5aeb53fc5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_avatars",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("mime", sa.String(length=40), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("user_avatars")
