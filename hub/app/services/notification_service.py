"""Per-user triage notifications (Epic 02). GitHub-style: collapse activity onto
one thread per (user, subject_key), keep the most-relevant reason, and let `done`
threads re-open only on high-signal reasons.

Authorization: every read/mutate is scoped to the requesting user's own rows. A
cross-user id is treated as not-found (never reveals another user's inbox)."""

from collections.abc import Awaitable, Callable

from app.models.notification import Notification
from app.models.user import User, utcnow
from app.repositories.notification_repo import NotificationRepository
from app.schemas.notification import NotificationOut
from app.services.errors import NotFoundError

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


class NotificationService:
    def __init__(
        self,
        notifications: NotificationRepository,
        publisher: NotificationPublisher | None = None,
    ) -> None:
        self._notifications = notifications
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
        """Creates or collapses a notification. Returns the row, or None when a
        low-signal event hit a `done` thread (no resurface)."""
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
