"""Per-user triage notifications (Epic 02). GitHub-style: collapse activity onto
one thread per (user, subject_key), keep the most-relevant reason, and let `done`
threads re-open only on high-signal reasons.

Authorization: every read/mutate is scoped to the requesting user's own rows. A
cross-user id is treated as not-found (never reveals another user's inbox)."""

from collections.abc import Awaitable, Callable

from app.models.notification import Notification, NotificationSubscription
from app.models.user import User, utcnow
from app.repositories.notification_repo import NotificationRepository
from app.repositories.user_repo import UserRepository
from app.schemas.notification import NOTIFY_LEVELS, SUBSCRIPTION_STATES, NotificationOut
from app.services.errors import InvalidInputError, NotFoundError

# Push sink for real-time deltas (Epic 02 · slice b). The composition root wires
# this to the connection manager; the service stays free of transport imports
# (dependency inversion — it only awaits an abstract callable).
NotificationPublisher = Callable[[int, dict], Awaitable[None]]

# Reason relevance (higher wins when a thread collapses). A thread that became a
# `mention` stays one even as low-signal activity piles on (GitHub semantics).
_PRIORITY = {
    "system": 0,
    "subscribed": 1,
    "participating": 1,
    "state_change": 1,
    "autorespond_completed": 1,
    "autorespond_blocked": 2,
    "direct_message": 2,
    "task_assigned": 3,
    "broadcast": 3,
    "team_mention": 4,
    "mention": 5,
    "escalation": 5,
    "approval_requested": 6,
    "security_alert": 7,
}

# Reasons strong enough to re-open a thread the user already marked `done`.
_HIGH_SIGNAL = frozenset(
    {"mention", "team_mention", "approval_requested", "broadcast", "security_alert", "escalation"}
)

MAX_LIMIT = 100

DEFAULT_NOTIFY_LEVEL = "mentions_and_direct"

# Always delivered, regardless of the recipient's notify_level (a muted inbox
# must still surface a direct @mention, a pending approval, or a security
# alert — silencing those would be a safety hole, not a convenience).
_ALWAYS_DELIVER = frozenset({"mention", "approval_requested", "security_alert"})
# The `mentions_and_direct` default adds direct/assigned/escalation on top.
_DELIVER_AT_DEFAULT = _ALWAYS_DELIVER | {
    "team_mention",
    "direct_message",
    "task_assigned",
    "escalation",
}


def should_deliver(notify_level: str, reason: str) -> bool:
    """The coarse delivery gate (Epic 02 · anti-spam). `all` delivers
    everything; `mute` lets only always-deliver reasons through;
    `mentions_and_direct` (and any unknown value — fail-safe) delivers direct
    activity and mentions but filters broadcast/auto-respond noise."""
    if notify_level == "all":
        return True
    if notify_level == "mute":
        return reason in _ALWAYS_DELIVER
    return reason in _DELIVER_AT_DEFAULT


class NotificationService:
    def __init__(
        self,
        notifications: NotificationRepository,
        users: UserRepository | None = None,
        publisher: NotificationPublisher | None = None,
    ) -> None:
        self._notifications = notifications
        self._users = users
        self._publisher = publisher

    async def _publish(self, notification: Notification) -> None:
        """Best-effort real-time push of a created/collapsed notification."""
        if self._publisher is None:
            return
        payload = {
            "type": "notification",
            "notification": NotificationOut.model_validate(notification).model_dump(mode="json"),
        }
        await self._publisher(notification.user_id, payload)

    async def notify(
        self,
        user_id: int,
        *,
        subject_type: str,
        subject_key: str,
        reason: str,
        title: str,
        link: str = "",
        actor: str = "",
        agent_slug: str | None = None,
    ) -> Notification | None:
        """Creates or collapses a notification. Returns the row, or None when the
        delivery gate filters it out / a low-signal event hit a `done` thread."""
        always_deliver = reason in _ALWAYS_DELIVER
        # Coarse gate: respect the recipient's notify_level (always-deliver
        # reasons pass it). A missing user fails safe to the default policy.
        if self._users is not None:
            recipient = await self._users.get_by_id(user_id)
            level = recipient.notify_level if recipient else DEFAULT_NOTIFY_LEVEL
            if not should_deliver(level, reason):
                return None
        # Fine gate: a per-thread `ignored` subscription mutes the thread, except
        # for always-deliver reasons — which also re-subscribe it (safe-mute: a
        # muted thread can never swallow a direct ping / approval / alert).
        subscription = await self._notifications.get_subscription(user_id, subject_key)
        if subscription is not None and subscription.state == "ignored":
            if not always_deliver:
                return None
            await self._notifications.upsert_subscription(
                user_id, subject_key, "subscribed", reason=reason
            )

        existing = await self._notifications.get_by_subject(user_id, subject_key)
        if existing is None:
            created = await self._notifications.add(
                Notification(
                    user_id=user_id,
                    subject_type=subject_type,
                    subject_key=subject_key,
                    agent_slug=agent_slug,
                    reason=reason,
                    title=title,
                    link=link,
                    actor=actor,
                )
            )
            await self._publish(created)
            return created

        if existing.status == "done" and reason not in _HIGH_SIGNAL:
            return None  # low-signal activity does not resurface a done thread

        # Collapse onto the existing thread.
        existing.title = title
        existing.actor = actor
        existing.link = link
        if agent_slug is not None:
            existing.agent_slug = agent_slug
        # Keep the most-relevant reason (mention sticks over participating, …).
        if _PRIORITY.get(reason, 1) >= _PRIORITY.get(existing.reason, 1):
            existing.reason = reason
        existing.unread = True
        existing.status = "inbox" if existing.status == "done" else existing.status
        existing.updated_at = utcnow()
        await self._notifications.save(existing)
        await self._publish(existing)
        return existing

    async def list(
        self,
        user: User,
        *,
        status: str | None = None,
        unread: bool | None = None,
        reason: str | None = None,
        agent_slug: str | None = None,
        limit: int = 50,
    ) -> list[Notification]:
        return await self._notifications.list_for_user(
            user.id,
            status=status,
            unread=unread,
            reason=reason,
            agent_slug=agent_slug,
            limit=min(max(limit, 1), MAX_LIMIT),
        )

    async def unread_count(self, user: User) -> int:
        return await self._notifications.unread_count(user.id)

    async def mark_all_read(self, user: User) -> None:
        await self._notifications.mark_all_read(user.id)

    def get_prefs(self, user: User) -> str:
        """The user's coarse delivery preference (already loaded on `user`)."""
        return user.notify_level

    async def set_prefs(self, user: User, notify_level: str) -> str:
        if notify_level not in NOTIFY_LEVELS:
            raise InvalidInputError("Nível de notificação inválido.")
        if self._users is None:  # pragma: no cover — always wired via deps
            raise InvalidInputError("Preferências indisponíveis.")
        user.notify_level = notify_level
        await self._users.save(user)
        return user.notify_level

    async def set_subscription(
        self, user: User, subject_key: str, state: str
    ) -> NotificationSubscription:
        """Follow (`subscribed`) or mute (`ignored`) a thread for this user."""
        if state not in SUBSCRIPTION_STATES:
            raise InvalidInputError("Estado de inscrição inválido.")
        return await self._notifications.upsert_subscription(user.id, subject_key, state)

    async def _owned(self, user: User, notification_id: int) -> Notification:
        notification = await self._notifications.get(notification_id)
        # Cross-user (or missing) id ⇒ not-found: never reveal another user's inbox.
        if notification is None or notification.user_id != user.id:
            raise NotFoundError("Notificação não encontrada.")
        return notification

    async def triage(
        self,
        user: User,
        notification_id: int,
        *,
        unread: bool | None = None,
        status: str | None = None,
    ) -> Notification:
        notification = await self._owned(user, notification_id)
        if unread is not None:
            notification.unread = unread
            if not unread:
                notification.last_read_at = utcnow()
        if status is not None:
            notification.status = status
        await self._notifications.save(notification)
        return notification
