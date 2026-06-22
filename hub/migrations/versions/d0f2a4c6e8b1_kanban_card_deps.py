"""kanban card dependencies (DAG) + columns.is_done terminal flag

Revision ID: d0f2a4c6e8b1
Revises: c9e1f3a5b7d2
Create Date: 2026-06-22 15:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.db import UTCDateTime

revision: str = "d0f2a4c6e8b1"
down_revision: str | None = "c9e1f3a5b7d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "kanban_columns",
        sa.Column("is_done", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Backfill: the rightmost column (max rank) of each existing board becomes a
    # terminal/done column, so dependency gating works for boards created before
    # this revision (new boards seed "Concluído" with is_done).
    op.execute(
        """
        UPDATE kanban_columns SET is_done = 1
        WHERE id IN (
            SELECT c.id FROM kanban_columns c
            WHERE c.rank = (
                SELECT MAX(c2.rank) FROM kanban_columns c2 WHERE c2.board_id = c.board_id
            )
        )
        """
    )

    op.create_table(
        "kanban_card_deps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("card_id", sa.Integer(), nullable=False),
        sa.Column("depends_on_id", sa.Integer(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["card_id"], ["kanban_cards.id"]),
        sa.ForeignKeyConstraint(["depends_on_id"], ["kanban_cards.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kanban_card_deps_card_id", "kanban_card_deps", ["card_id"])
    op.create_index("ix_kanban_card_deps_depends_on_id", "kanban_card_deps", ["depends_on_id"])
    op.create_index(
        "ix_kanban_card_deps_pair", "kanban_card_deps", ["card_id", "depends_on_id"], unique=True
    )


def downgrade() -> None:
    op.drop_table("kanban_card_deps")
    op.drop_column("kanban_columns", "is_done")
