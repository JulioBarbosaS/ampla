from datetime import datetime

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message
from app.models.user import utcnow


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, message: Message) -> Message:
        self._session.add(message)
        await self._session.flush()  # garante o id antes de fechar a thread
        if message.thread_id is None:
            message.thread_id = message.id  # mensagem raiz inicia a própria thread
        await self._session.commit()
        await self._session.refresh(message)
        return message

    async def get(self, message_id: int) -> Message | None:
        return await self._session.get(Message, message_id)

    async def save(self, message: Message) -> None:
        self._session.add(message)
        await self._session.commit()

    async def conversation(self, agent_a: str, agent_b: str, limit: int = 50) -> list[Message]:
        """Mensagens entre dois agentes, mais recentes primeiro."""
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
        """Não entregues nem expiradas, mais antigas primeiro (ordem de entrega)."""
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
        """Mensagens que envolvem qualquer um dos slugs (para listar conversas)."""
        if not agent_slugs:
            return []
        result = await self._session.execute(
            select(Message)
            .where(or_(Message.from_agent.in_(agent_slugs), Message.to_agent.in_(agent_slugs)))
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
        )
        return list(result.scalars())
