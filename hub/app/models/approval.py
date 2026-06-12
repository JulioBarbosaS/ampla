from datetime import datetime

from sqlalchemy import Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UTCDateTime
from app.models.user import utcnow


class Approval(Base):
    """A drafted auto-reply awaiting the agent owner's decision (Epic 03 · 3.3).

    When an agent has require_approval set, the daemon drafts the reply
    (guardrails + secret filter already applied) and requests approval instead
    of sending. The owner approves / edits / rejects in the panel and the hub
    sends server-side, so it works even if the daemon later disconnects.

    Security: `draft_body` is agent-authored → stored as PLAIN TEXT, rendered as
    sanitized Markdown. The row is attributed to the socket's AUTHENTICATED
    `agent_slug` (anti-spoof, like the autorespond report).
    """

    __tablename__ = "approvals"
    __table_args__ = (Index("ix_approvals_agent_status", "agent_slug", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_slug: Mapped[str] = mapped_column(String(60), index=True)
    trigger_message_id: Mapped[int | None] = mapped_column(default=None)
    to_agent: Mapped[str] = mapped_column(String(60))
    draft_body: Mapped[str] = mapped_column(Text)
    # pending | approved | rejected | edited
    status: Mapped[str] = mapped_column(String(12), default="pending")
    decided_by: Mapped[int | None] = mapped_column(default=None)  # user id
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
