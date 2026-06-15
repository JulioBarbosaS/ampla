from datetime import datetime

from sqlalchemy import JSON, Float, ForeignKey, String, Text
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

    # Daily auto-respond budget (Epic 03 · 3.4): a hard ceiling on spend per
    # local day. None = unlimited. The daemon enforces these against captured
    # usage (only when capture_usage is on), skipping with reason budget_exceeded.
    max_auto_tokens_per_day: Mapped[int | None] = mapped_column(default=None)
    max_auto_cost_usd_per_day: Mapped[float | None] = mapped_column(Float, default=None)

    # Human-in-the-loop approval (Epic 03 · 3.3): when true and mode=auto, the
    # daemon DRAFTS the reply but does not send it — it requests the owner's
    # approval first. (server_default lives in the migration, like the others.)
    require_approval: Mapped[bool] = mapped_column(default=False)

    # Availability window / DND (Epic 04 · 4.2): null = always-on. When set, the
    # daemon only auto-responds inside the windows (in the schedule's tz),
    # otherwise behaves like inbox. Shape validated by the AutoSchedule schema.
    auto_schedule: Mapped[dict | None] = mapped_column(JSON, default=None)

    # Escalation routing (Epic 04 · 4.3): which auto-respond outcomes route the
    # trigger message to the owner's Inbox (reason `escalation`) instead of being
    # silently dropped. This is a HUB-SIDE policy — the daemon reports every run
    # and the hub decides escalation from the report — so it is deliberately NOT
    # part of the WS AgentSettings (the daemon never needs it). Default escalates
    # hard failures; [] = never escalate. (server_default in the migration, like
    # the other JSON guardrail columns.)
    escalate_on: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["failed", "blocked"])


class AgentKey(Base):
    __tablename__ = "agent_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_slug: Mapped[str] = mapped_column(ForeignKey("agents.slug"), index=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # sha256 hex digest
    label: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
