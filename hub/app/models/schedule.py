"""Scheduled agent tasks (Epic 08): an agent wakes on a schedule and runs a
trusted, owner-authored prompt. Owner/admin manage the schedule via REST; the
in-process engine fires due ones over the WS.

Security (docs/ARCHITECTURE.md): the `prompt` is owner-authored — the one place
an agent is driven by *trusted* input (contrast: inbound messages are untrusted
and run with --strict-mcp-config). `created_by` is the authenticated actor. Every
fire is audited; the global kill switch and per-agent pause suppress it.
"""

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UTCDateTime
from app.models.user import utcnow


class AgentSchedule(Base):
    __tablename__ = "agent_schedules"
    # The engine's hot query: due = enabled AND next_run_at <= now.
    __table_args__ = (Index("ix_agent_schedules_due", "enabled", "next_run_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    agent_slug: Mapped[str] = mapped_column(String(60), index=True)  # the agent that wakes
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(8))  # cron | interval | once
    spec: Mapped[str] = mapped_column(String(120))  # cron expr | seconds | ISO instant
    prompt: Mapped[str] = mapped_column(Text)  # owner-authored ⇒ trusted
    # Guardrail level the run gets (reuses the auto-respond posture): read | write.
    tools: Mapped[str] = mapped_column(String(20), default="read")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Engine-managed scheduling state.
    next_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None, index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    # ok | skipped_offline | failed | blocked | None (never run)
    last_status: Mapped[str | None] = mapped_column(String(16), default=None)
    created_by: Mapped[str] = mapped_column(String(60))  # authenticated actor
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
