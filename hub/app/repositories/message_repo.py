from datetime import datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message
from app.models.user import utcnow


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, message: Message) -> Message:
        self._session.add(message)
        await self._session.flush()  # ensure the id before closing the thread
        if message.thread_id is None:
            message.thread_id = message.id  # a root message starts its own thread
        await self._session.commit()
        await self._session.refresh(message)
        return message

    async def get(self, message_id: int) -> Message | None:
        return await self._session.get(Message, message_id)

    async def count_since(self, since: datetime) -> int:
        """Total messages routed in the window (instance throughput)."""
        return (
            await self._session.execute(
                select(func.count(Message.id)).where(Message.created_at >= since)
            )
        ).scalar_one()

    async def save(self, message: Message) -> None:
        self._session.add(message)
        await self._session.commit()

    async def conversation(self, agent_a: str, agent_b: str, limit: int = 50) -> list[Message]:
        """Messages between two agents, most recent first."""
        result = await self._session.execute(
            select(Message)
            .where(
                or_(
                    (Message.from_agent == agent_a) & (Message.to_agent == agent_b),
                    (Message.from_agent == agent_b) & (Message.to_agent == agent_a),
                )
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
        )
        return list(result.scalars())

    async def pending_for(self, to_agent: str) -> list[Message]:
        """Neither delivered nor expired, oldest first (delivery order)."""
        result = await self._session.execute(
            select(Message)
            .where(
                Message.to_agent == to_agent,
                Message.delivered_at.is_(None),
                or_(Message.expires_at.is_(None), Message.expires_at > utcnow()),
            )
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        return list(result.scalars())

    async def mark_delivered(self, message_ids: list[int], when: datetime | None = None) -> None:
        if not message_ids:
            return
        await self._session.execute(
            update(Message).where(Message.id.in_(message_ids)).values(delivered_at=when or utcnow())
        )
        await self._session.commit()

    async def involving(self, agent_slugs: list[str], limit: int = 200) -> list[Message]:
        """Messages involving any of the slugs (for listing conversations)."""
        if not agent_slugs:
            return []
        result = await self._session.execute(
            select(Message)
            .where(or_(Message.from_agent.in_(agent_slugs), Message.to_agent.in_(agent_slugs)))
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
        )
        return list(result.scalars())
