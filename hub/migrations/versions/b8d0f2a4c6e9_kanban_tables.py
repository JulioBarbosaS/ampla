"""kanban tables (boards, columns, cards, comments, agent grants)

Revision ID: b8d0f2a4c6e9
Revises: a7c9e1b3d5f7
Create Date: 2026-06-18 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.db import UTCDateTime

revision: str = "b8d0f2a4c6e9"
down_revision: str | None = "a7c9e1b3d5f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "kanban_boards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("visibility", sa.String(length=8), nullable=False),
        sa.Column("default_agent_role", sa.String(length=12), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kanban_boards_owner_id", "kanban_boards", ["owner_id"])

    op.create_table(
        "kanban_columns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("board_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("rank", sa.String(length=64), nullable=False),
        sa.Column("wip_limit", sa.Integer(), nullable=True),
        sa.Column("is_landing", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["board_id"], ["kanban_boards.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kanban_columns_board_id", "kanban_columns", ["board_id"])

    op.create_table(
        "kanban_cards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("board_id", sa.Integer(), nullable=False),
        sa.Column("column_id", sa.Integer(), nullable=False),
        sa.Column("rank", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=60), nullable=False),
        sa.Column("assignee", sa.String(length=60), nullable=True),
        sa.Column("priority", sa.String(length=8), nullable=False),
        sa.Column("origin", sa.JSON(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["board_id"], ["kanban_boards.id"]),
        sa.ForeignKeyConstraint(["column_id"], ["kanban_columns.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kanban_cards_board_id", "kanban_cards", ["board_id"])
    op.create_index("ix_kanban_cards_column_id", "kanban_cards", ["column_id"])
    op.create_index(
        "ix_kanban_cards_column_rank", "kanban_cards", ["column_id", "rank"], unique=True
    )

    op.create_table(
        "kanban_card_comments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("card_id", sa.Integer(), nullable=False),
        sa.Column("author", sa.String(length=60), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["card_id"], ["kanban_cards.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kanban_card_comments_card_id", "kanban_card_comments", ["card_id"])

    op.create_table(
        "kanban_agent_grants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("board_id", sa.Integer(), nullable=False),
        sa.Column("agent_slug", sa.String(length=60), nullable=False),
        sa.Column("role", sa.String(length=12), nullable=False),
        sa.ForeignKeyConstraint(["board_id"], ["kanban_boards.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kanban_agent_grants_board_id", "kanban_agent_grants", ["board_id"])
    op.create_index(
        "ix_kanban_grants_board_agent",
        "kanban_agent_grants",
        ["board_id", "agent_slug"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("kanban_agent_grants")
    op.drop_table("kanban_card_comments")
    op.drop_index("ix_kanban_cards_column_rank", table_name="kanban_cards")
    op.drop_table("kanban_cards")
    op.drop_table("kanban_columns")
    op.drop_table("kanban_boards")
