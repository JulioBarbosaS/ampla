"""kanban board members (per-user board sharing — Epic 10)

Revision ID: f2b4d6c8e0a1
Revises: e1a3c5b7d9f2
Create Date: 2026-06-23 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.db import UTCDateTime

revision: str = "f2b4d6c8e0a1"
down_revision: str | None = "e1a3c5b7d9f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # New table, no backfill: existing boards simply have no extra members yet
    # (their owner + team visibility are unchanged).
    op.create_table(
        "kanban_board_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("board_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["board_id"], ["kanban_boards.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kanban_board_members_board_id", "kanban_board_members", ["board_id"])
    op.create_index("ix_kanban_board_members_user_id", "kanban_board_members", ["user_id"])
    op.create_index(
        "ix_kanban_board_members_pair",
        "kanban_board_members",
        ["board_id", "user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("kanban_board_members")
