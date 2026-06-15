"""agent escalate_on (escalation routing to the owner inbox)

Revision ID: f6a8c0e2b4d5
Revises: e5a7c9b1d3f4
Create Date: 2026-06-15 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a8c0e2b4d5"
down_revision: str | None = "e5a7c9b1d3f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default backfills existing rows with the same default the ORM uses
    # (escalate hard failures). A JSON text literal, like denied_paths/trusted_senders.
    with op.batch_alter_table("agents", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "escalate_on",
                sa.JSON(),
                nullable=False,
                server_default=sa.text('\'["failed", "blocked"]\''),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("agents", schema=None) as batch_op:
        batch_op.drop_column("escalate_on")
