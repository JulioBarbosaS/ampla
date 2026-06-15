"""guardrail_presets table (reusable guardrail bundles)

Revision ID: e5a7c9b1d3f4
Revises: d4f6a8c0e2b3
Create Date: 2026-06-13 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.db import UTCDateTime

revision: str = "e5a7c9b1d3f4"
down_revision: str | None = "d4f6a8c0e2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "guardrail_presets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_guardrail_presets_owner_id", "guardrail_presets", ["owner_id"])
    op.create_index(
        "ix_presets_owner_name", "guardrail_presets", ["owner_id", "name"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_presets_owner_name", table_name="guardrail_presets")
    op.drop_index("ix_guardrail_presets_owner_id", table_name="guardrail_presets")
    op.drop_table("guardrail_presets")
