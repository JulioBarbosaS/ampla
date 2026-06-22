"""kanban boards: opt-in event-card flags (delegation/escalation → card)

Revision ID: c9e1f3a5b7d2
Revises: b8d0f2a4c6e9
Create Date: 2026-06-22 14:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9e1f3a5b7d2"
down_revision: str | None = "b8d0f2a4c6e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default "0" backfills existing boards as opted-out (Epic 06 · 6.5).
    op.add_column(
        "kanban_boards",
        sa.Column(
            "auto_card_on_delegation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "kanban_boards",
        sa.Column(
            "auto_card_on_escalation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("kanban_boards", "auto_card_on_escalation")
    op.drop_column("kanban_boards", "auto_card_on_delegation")
