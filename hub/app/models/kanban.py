"""Kanban / task board (Epic 06). A shared board where humans and agents
collaborate on cards, gated by a per-agent, per-board permission model.

Security (docs/ARCHITECTURE.md): `created_by`/`author` are the AUTHENTICATED
actor (`user:<id>` or an agent slug), never client-claimed (anti-spoof). Card
ordering uses a fractional `rank` string (LexoRank-style) so a move rewrites only
the moved card; concurrency is handled in the service layer (serialized write
transaction + optimistic `version`). Every mutation is audited.
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UTCDateTime
from app.models.user import utcnow


class KanbanBoard(Base):
    __tablename__ = "kanban_boards"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    # team = every member can edit; private = owner + grantees only.
    visibility: Mapped[str] = mapped_column(String(8), default="team")
    # Role an agent gets WITHOUT an explicit grant. Default `none` = dev-only board.
    default_agent_role: Mapped[str] = mapped_column(String(12), default="none")
    # Opt-in event cards (Epic 06 · 6.5): when on, a delegation/escalation whose
    # target's owner owns THIS board drops a card here automatically. Off by
    # default — most boards never auto-create cards. (server_default in migration.)
    auto_card_on_delegation: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_card_on_escalation: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class KanbanColumn(Base):
    __tablename__ = "kanban_columns"

    id: Mapped[int] = mapped_column(primary_key=True)
    board_id: Mapped[int] = mapped_column(ForeignKey("kanban_boards.id"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    rank: Mapped[str] = mapped_column(String(64))  # column order (same scheme as cards)
    wip_limit: Mapped[int | None] = mapped_column(Integer, default=None)  # null = unlimited
    # New cards / event-driven cards land here (exactly one per board).
    is_landing: Mapped[bool] = mapped_column(Boolean, default=False)
    # Terminal column: a card here counts as "done" for dependency gating
    # (Epic 06 · 6.7 DAG). Seeded on "Concluído"; a board may have several.
    is_done: Mapped[bool] = mapped_column(Boolean, default=False)


class KanbanCard(Base):
    __tablename__ = "kanban_cards"
    __table_args__ = (
        # Backstop against midpoint collisions on concurrent moves (Epic 06 · 6.2).
        Index("ix_kanban_cards_column_rank", "column_id", "rank", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    board_id: Mapped[int] = mapped_column(ForeignKey("kanban_boards.id"), index=True)
    column_id: Mapped[int] = mapped_column(ForeignKey("kanban_columns.id"), index=True)
    rank: Mapped[str] = mapped_column(String(64))  # order WITHIN the column
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(60))  # authenticated actor (anti-spoof)
    assignee: Mapped[str | None] = mapped_column(String(60), default=None)
    priority: Mapped[str] = mapped_column(String(8), default="normal")
    # {kind: message|thread|delegation|escalation, id} — links a card to its origin.
    origin: Mapped[dict | None] = mapped_column(JSON, default=None)
    # Optimistic-concurrency counter: bumped on every mutation; a stale move/edit
    # is rejected with 409 (Epic 06 · 6.2).
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class KanbanCardComment(Base):
    __tablename__ = "kanban_card_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("kanban_cards.id"), index=True)
    author: Mapped[str] = mapped_column(String(60))  # authenticated actor (anti-spoof)
    body: Mapped[str] = mapped_column(Text)  # untrusted → rendered as sanitized Markdown
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class KanbanAgentGrant(Base):
    """Per-agent, per-board role (Epic 06 · 6.3). Absence + board.default_agent_role
    decides access. Roles: viewer | contributor | editor. Restricts AGENTS only —
    human members keep full edit."""

    __tablename__ = "kanban_agent_grants"
    __table_args__ = (Index("ix_kanban_grants_board_agent", "board_id", "agent_slug", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    board_id: Mapped[int] = mapped_column(ForeignKey("kanban_boards.id"), index=True)
    agent_slug: Mapped[str] = mapped_column(String(60))
    role: Mapped[str] = mapped_column(String(12))


class KanbanBoardMember(Base):
    """A human shared onto a board (Epic 10). A member sees and edits the board
    like a team member would, and may grant their OWN agents a role on it; board
    governance (settings, members, delete) stays owner/admin only. Membership is
    what lets a *private* board be shared with specific people instead of the
    whole team. Unique per (board, user)."""

    __tablename__ = "kanban_board_members"
    __table_args__ = (Index("ix_kanban_board_members_pair", "board_id", "user_id", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    board_id: Mapped[int] = mapped_column(ForeignKey("kanban_boards.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class KanbanCardDep(Base):
    """A blocking dependency between cards (Epic 06 · 6.7 DAG): `card_id` is
    blocked until `depends_on_id` reaches a `is_done` column. Both cards live on
    the same board; the service rejects self-edges and any edge that would close
    a cycle. Unique per (card, dependency)."""

    __tablename__ = "kanban_card_deps"
    __table_args__ = (Index("ix_kanban_card_deps_pair", "card_id", "depends_on_id", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("kanban_cards.id"), index=True)
    depends_on_id: Mapped[int] = mapped_column(ForeignKey("kanban_cards.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
