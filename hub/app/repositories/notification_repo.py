from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.models.user import utcnow


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, notification: Notification) -> Notification:
        self._session.add(notification)
        await self._session.commit()
        await self._session.refresh(notification)
        return notification

    async def save(self, notification: Notification) -> None:
        self._session.add(notification)
        await self._session.commit()

    async def get(self, notification_id: int) -> Notification | None:
        return await self._session.get(Notification, notification_id)

    async def get_by_subject(self, user_id: int, subject_key: str) -> Notification | None:
        """The existing thread for collapsing (one row per user+subject)."""
        result = await self._session.execute(
            select(Notification).where(
                Notification.user_id == user_id, Notification.subject_key == subject_key
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: int,
        *,
        status: str | None = None,
        unread: bool | None = None,
        reason: str | None = None,
        agent_slug: str | None = None,
        limit: int = 50,
    ) -> list[Notification]:
        stmt = select(Notification).where(Notification.user_id == user_id)
        if status is not None:
            stmt = stmt.where(Notification.status == status)
        if unread is not None:
            stmt = stmt.where(Notification.unread == unread)
        if reason is not None:
            stmt = stmt.where(Notification.reason == reason)
        if agent_slug is not None:
            stmt = stmt.where(Notification.agent_slug == agent_slug)
        stmt = stmt.order_by(Notification.updated_at.desc(), Notification.id.desc()).limit(limit)
        return list((await self._session.execute(stmt)).scalars())

    async def unread_count(self, user_id: int) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.unread.is_(True))
        )
        return int(result.scalar_one())

    async def mark_all_read(self, user_id: int) -> None:
        """Bulk-clear unread for one user (single UPDATE, never another user's)."""
        await self._session.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.unread.is_(True))
            .values(unread=False, last_read_at=utcnow())
        )
        await self._session.commit()
