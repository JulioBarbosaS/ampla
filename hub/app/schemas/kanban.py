"""Kanban board schemas (Epic 06). Bodies/titles are untrusted (agent- or
human-authored) → bounded here and rendered as sanitized Markdown by the panel.
`created_by`/`author`/`assignee` are NEVER taken from the client: the service
stamps the authenticated actor (anti-spoof, docs/ARCHITECTURE.md)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.message import PRIORITY_PATTERN

# Visibility + per-agent role vocabularies (mirrored where the daemon/panel need them).
VISIBILITY_VALUES = ("team", "private")
# Roles an AGENT can hold on a board. `none` = no access (dev-only board).
AGENT_ROLES = ("none", "viewer", "contributor", "editor")
VISIBILITY_PATTERN = r"^(team|private)$"
AGENT_ROLE_PATTERN = r"^(none|viewer|contributor|editor)$"
# Grantable roles (a grant of `none` is just a revoke — handled by DELETE).
GRANTABLE_ROLES = ("viewer", "contributor", "editor")
GRANT_ROLE_PATTERN = r"^(viewer|contributor|editor)$"

# Size bounds (untrusted input).
KANBAN_CARD_BODY_MAX = 16384
KANBAN_COMMENT_BODY_MAX = 16384
KANBAN_TITLE_MAX = 200
KANBAN_BOARD_NAME_MAX = 120
KANBAN_COLUMN_NAME_MAX = 60
KANBAN_ACTOR_MAX = 60  # `user:<id>` or an agent slug


# ---- boards ----


class BoardCreate(BaseModel):
    name: str = Field(min_length=1, max_length=KANBAN_BOARD_NAME_MAX)
    visibility: str = Field(default="team", pattern=VISIBILITY_PATTERN)
    default_agent_role: str = Field(default="none", pattern=AGENT_ROLE_PATTERN)


class BoardUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=KANBAN_BOARD_NAME_MAX)
    visibility: str | None = Field(default=None, pattern=VISIBILITY_PATTERN)
    default_agent_role: str | None = Field(default=None, pattern=AGENT_ROLE_PATTERN)


class BoardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    name: str
    visibility: str
    default_agent_role: str
    created_at: datetime


# ---- columns ----


class ColumnCreate(BaseModel):
    name: str = Field(min_length=1, max_length=KANBAN_COLUMN_NAME_MAX)
    wip_limit: int | None = Field(default=None, ge=1, le=999)


class ColumnUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=KANBAN_COLUMN_NAME_MAX)
    # 0 clears the WIP limit (unlimited); a positive value sets it; null = unchanged.
    wip_limit: int | None = Field(default=None, ge=0, le=999)
    is_landing: bool | None = None


class ColumnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    board_id: int
    name: str
    rank: str
    wip_limit: int | None
    is_landing: bool


# ---- cards ----


class CardCreate(BaseModel):
    title: str = Field(min_length=1, max_length=KANBAN_TITLE_MAX)
    body: str = Field(default="", max_length=KANBAN_CARD_BODY_MAX)
    # Defaults to the board's landing column when omitted.
    column_id: int | None = None
    assignee: str | None = Field(default=None, max_length=KANBAN_ACTOR_MAX)
    priority: str = Field(default="normal", pattern=PRIORITY_PATTERN)


class CardUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=KANBAN_TITLE_MAX)
    body: str | None = Field(default=None, max_length=KANBAN_CARD_BODY_MAX)
    assignee: str | None = Field(default=None, max_length=KANBAN_ACTOR_MAX)
    clear_assignee: bool = False  # assignee=null is ambiguous in a PATCH
    priority: str | None = Field(default=None, pattern=PRIORITY_PATTERN)
    # Optimistic-concurrency guard (Epic 06 · 6.2): if set and stale → 409.
    expected_version: int | None = Field(default=None, ge=1)


class CardMove(BaseModel):
    """Anchor-based move intent (Epic 06 · 6.2): place the card in `to_column_id`
    between the neighbours the client saw (`before_id`/`after_id`), guarded by
    `expected_version`. Never a raw numeric index — the server recomputes the
    rank from the current neighbours so a stale view can't misorder."""

    to_column_id: int
    before_id: int | None = None
    after_id: int | None = None
    expected_version: int = Field(ge=1)


class CardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    board_id: int
    column_id: int
    rank: str
    title: str
    body: str
    created_by: str
    assignee: str | None
    priority: str
    origin: dict | None
    version: int
    created_at: datetime
    updated_at: datetime


# ---- comments ----


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=KANBAN_COMMENT_BODY_MAX)


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    card_id: int
    author: str
    body: str
    created_at: datetime


# ---- aggregate (initial render) ----


class BoardFull(BaseModel):
    """Board + its columns + its cards in one payload for the first render."""

    board: BoardOut
    columns: list[ColumnOut]
    cards: list[CardOut]
