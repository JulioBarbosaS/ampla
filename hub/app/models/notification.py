from datetime import datetime

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UTCDateTime
from app.models.user import utcnow


class Notification(Base):
    """A per-USER triage notification (Epic 02), GitHub-notifications style: a
    thread about a subject, carrying a reason, moving through unread × status.

    Distinct from the daemon's per-agent local inbox — this is the human
    operator's triage surface in the panel, aggregating everything that concerns
    any of their agents.

    Security: `title`/`actor` may derive from agent-authored content, so they are
    stored and rendered as PLAIN TEXT (never markdown/HTML). `link` is built by
    the hub from validated ids, never from agent text.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_inbox", "user_id", "status", "updated_at"),
        Index("ix_notifications_subject", "user_id", "subject_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(index=True)  # owner of the inbox
    subject_type: Mapped[str] = mapped_column(String(16))  # dm|mention|task|broadcast|approval|…
    subject_key: Mapped[str] = mapped_column(String(120))  # stable grouping key (collapsing)
    agent_slug: Mapped[str | None] = mapped_column(String(60), default=None)  # which owned agent
    reason: Mapped[str] = mapped_column(String(24))  # most-relevant current reason
    title: Mapped[str] = mapped_column(String(200))  # plain-text summary
    link: Mapped[str] = mapped_column(String(255), default="")
    actor: Mapped[str] = mapped_column(String(120), default="")
    unread: Mapped[bool] = mapped_column(default=True)
    status: Mapped[str] = mapped_column(String(8), default="inbox")  # inbox|saved|done
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    last_read_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)


class NotificationSubscription(Base):
    """Fine-grained per-thread override on top of the coarse `notify_level`
    (Epic 02, the GitHub two-layer subscription model). `ignored` mutes a thread
    even when the coarse watch would deliver it; `subscribed` follows it.

    Safe-mute: an always-deliver reason (mention / approval_requested /
    security_alert) re-subscribes a muted thread — muting can never silence a
    direct ping, a pending approval, or a security alert.
    """

    __tablename__ = "notification_subscriptions"
    __table_args__ = (Index("ix_notif_subs_user_subject", "user_id", "subject_key", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(index=True)
    subject_key: Mapped[str] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(10))  # subscribed | ignored
    reason: Mapped[str | None] = mapped_column(String(24), default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
