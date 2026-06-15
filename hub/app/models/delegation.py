from datetime import datetime

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UTCDateTime
from app.models.user import utcnow


class Delegation(Base):
    """An agent-to-agent task hand-off (Epic 04 · 4.4).

    An interactive agent (a human-operated Claude session, via the `amp_delegate`
    MCP tool) hands a task to another agent WITH context; the result comes back
    when the delegate replies in-thread.

    Security: auto-responding agents CANNOT delegate — `claude -p` runs with
    `--strict-mcp-config` (no `ampla` MCP), so a delegation is structurally a
    human-in-the-loop action. That is what prevents agent↔agent runaway: an
    auto-reply can never spawn a further delegation. `from_agent` is the socket's
    AUTHENTICATED slug, never client-claimed (anti-spoof, like the approval/report
    frames). The handed `context` is untrusted to the delegate and reaches it
    delimited inside the task message body (like any incoming message).
    """

    __tablename__ = "delegations"
    __table_args__ = (Index("ix_delegations_from_status", "from_agent", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    from_agent: Mapped[str] = mapped_column(String(60), index=True)  # delegator (authenticated)
    to_agent: Mapped[str] = mapped_column(String(60), index=True)  # delegate
    task: Mapped[str] = mapped_column(String(2000))  # the headline (context goes in the message)
    root_message_id: Mapped[int | None] = mapped_column(default=None)  # the task message sent to B
    result_message_id: Mapped[int | None] = mapped_column(default=None)  # B's answer, when it lands
    # open | completed | declined  (declined = B's allowlist blocked the delegator)
    status: Mapped[str] = mapped_column(String(12), default="open")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
