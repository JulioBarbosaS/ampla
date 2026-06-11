from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UTCDateTime
from app.models.user import utcnow


class Agent(Base):
    """A user's agent. The PK is the public slug (e.g. backend-julio).

    Settings live here and are the source of truth — the daemon receives a copy
    via hello_ack/settings_update (docs/ARCHITECTURE.md · WS protocol).
    """

    __tablename__ = "agents"

    slug: Mapped[str] = mapped_column(String(60), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    # Settings (safe defaults — Threat 1: an agent starts in inbox, never auto)
    mode: Mapped[str] = mapped_column(String(10), default="inbox")  # inbox | auto
    allowed_senders: Mapped[list[str] | None] = mapped_column(JSON, default=None)  # None = everyone
    max_auto_per_hour: Mapped[int] = mapped_column(default=10)
    auto_timeout_secs: Mapped[int] = mapped_column(default=120)
    instructions: Mapped[str] = mapped_column(Text, default="")

    # Auto-respond filesystem guardrails (safe defaults; the daemon enforces them
    # as claude -p deny-rules). trusted_senders bypass them entirely.
    allow_write: Mapped[bool] = mapped_column(default=False)
    block_hidden_files: Mapped[bool] = mapped_column(default=True)
    block_sensitive_paths: Mapped[bool] = mapped_column(default=True)
    confine_to_dir: Mapped[bool] = mapped_column(default=True)
    denied_paths: Mapped[list[str]] = mapped_column(JSON, default=list)
    trusted_senders: Mapped[list[str]] = mapped_column(JSON, default=list)

    # Per-agent pause (Epic 03 · kill switch): a fast brake that takes the agent
    # out of auto-respond WITHOUT changing `mode`. When true the daemon enqueues
    # to the inbox only (no claude -p), so the owner can flip it back to exactly
    # the mode it had. Distinct from `mode` precisely so it is reversible.
    # (server_default lives in the migration, like the other guardrail columns.)
    auto_paused: Mapped[bool] = mapped_column(default=False)


class AgentKey(Base):
    __tablename__ = "agent_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_slug: Mapped[str] = mapped_column(ForeignKey("agents.slug"), index=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # sha256 hex digest
    label: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
