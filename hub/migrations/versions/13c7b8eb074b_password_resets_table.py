"""password resets table

Revision ID: 13c7b8eb074b
Revises: 3fa2df0ee39d
Create Date: 2026-06-10 12:13:29.663121
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.db import UTCDateTime

revision: str = "13c7b8eb074b"
down_revision: str | None = "3fa2df0ee39d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "password_resets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", UTCDateTime(), nullable=False),
        sa.Column("used_at", UTCDateTime(), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("password_resets", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_password_resets_token_hash"), ["token_hash"], unique=True
        )
        batch_op.create_index(
            batch_op.f("ix_password_resets_user_id"), ["user_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("password_resets", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_password_resets_user_id"))
        batch_op.drop_index(batch_op.f("ix_password_resets_token_hash"))
    op.drop_table("password_resets")
