from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# Reason enum (agent-domain analog of GitHub's reason). Stored as the
# most-relevant current reason for a collapsed thread.
REASONS = frozenset(
    {
        "mention",
        "direct_message",
        "task_assigned",
        "approval_requested",
        "autorespond_completed",
        "autorespond_blocked",
        "broadcast",
        "team_mention",
        "participating",
        "subscribed",
        "state_change",
        "security_alert",
        "escalation",
        "system",
    }
)

STATUSES = ("inbox", "saved", "done")

# Coarse delivery gate (the GitHub repo-watch analog). `mute` lets only the
# always-deliver reasons through; `mentions_and_direct` is the safe default.
NOTIFY_LEVELS = ("all", "mentions_and_direct", "mute")

# Fine per-thread override on top of the coarse level.
SUBSCRIPTION_STATES = ("subscribed", "ignored")


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subject_type: str
    subject_key: str
    agent_slug: str | None
    reason: str
    title: str
    link: str
    actor: str
    unread: bool
    status: str
    created_at: datetime
    updated_at: datetime
    last_read_at: datetime | None


class NotificationPatch(BaseModel):
    """Triage one notification: mark read/unread and/or move inbox|saved|done."""

    unread: bool | None = None
    status: str | None = Field(default=None, pattern=r"^(inbox|saved|done)$")


class UnreadCount(BaseModel):
    unread_count: int


class NotificationPrefs(BaseModel):
    """The user's coarse delivery preference (notify_level)."""

    notify_level: str


class NotificationPrefsPatch(BaseModel):
    notify_level: str = Field(pattern=r"^(all|mentions_and_direct|mute)$")


class SubscriptionPut(BaseModel):
    """Follow or mute a thread (per-thread override on the coarse level)."""

    subject_key: str = Field(min_length=1, max_length=120)
    state: str = Field(pattern=r"^(subscribed|ignored)$")


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    subject_key: str
    state: str
