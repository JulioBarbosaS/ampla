from datetime import datetime

from sqlalchemy import JSON, Float, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UTCDateTime
from app.models.user import utcnow


class AutorespondRun(Base):
    """An auditable record of one auto-respond run (Epic 03 · 3.1).

    Born in the daemon (the only place that sees the run) and pushed to the hub
    over the authenticated WS as an AutorespondReportFrame. The owner/admin can
    review exactly what each Claude did when poked from outside.

    Privacy: the prompt is NEVER stored (it carries the owner's instructions +
    conversation, which already lives in message history). Only a bounded
    `reply_preview` + metadata are kept (docs/specs/03-autorespond-trust.md).
    """

    __tablename__ = "autorespond_runs"
    __table_args__ = (Index("ix_autorespond_runs_agent", "agent_slug", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # The responding agent. Always the WS socket's authenticated slug — never a
    # value the daemon can claim (anti-spoof, like ack).
    agent_slug: Mapped[str] = mapped_column(String(60))
    trigger_message_id: Mapped[int | None] = mapped_column(default=None)
    from_sender: Mapped[str] = mapped_column(String(60))
    result: Mapped[str] = mapped_column(String(16))  # replied|blocked|failed|skipped
    reason: Mapped[str | None] = mapped_column(Text, default=None)
    reply_preview: Mapped[str] = mapped_column(Text, default="")
    tools_allowed: Mapped[str] = mapped_column(Text, default="")
    tools_disallowed: Mapped[str] = mapped_column(Text, default="")
    # Snapshot of the guardrails in effect: {allow_write, block_hidden_files,
    # block_sensitive_paths, confine_to_dir, trusted_sender, sandbox}.
    guardrails: Mapped[dict] = mapped_column(JSON, default=dict)
    duration_ms: Mapped[int] = mapped_column(default=0)
    timed_out: Mapped[bool] = mapped_column(default=False)
    # Best-effort usage (populated once 3.4 parses claude -p --output-format json).
    input_tokens: Mapped[int | None] = mapped_column(default=None)
    output_tokens: Mapped[int | None] = mapped_column(default=None)
    cost_usd: Mapped[float | None] = mapped_column(Float, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
