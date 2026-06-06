from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent, AgentKey


class AgentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, slug: str) -> Agent | None:
        return await self._session.get(Agent, slug)

    async def list_by_user(self, user_id: int) -> list[Agent]:
        result = await self._session.execute(
            select(Agent).where(Agent.user_id == user_id).order_by(Agent.slug)
        )
        return list(result.scalars())

    async def list_all(self) -> list[Agent]:
        result = await self._session.execute(select(Agent).order_by(Agent.slug))
        return list(result.scalars())

    async def add(self, agent: Agent) -> Agent:
        self._session.add(agent)
        await self._session.commit()
        await self._session.refresh(agent)
        return agent

    async def save(self, agent: Agent) -> None:
        self._session.add(agent)
        await self._session.commit()

    # ---- chaves ----

    async def add_key(self, key: AgentKey) -> AgentKey:
        self._session.add(key)
        await self._session.commit()
        await self._session.refresh(key)
        return key

    async def get_key_by_hash(self, key_hash: str) -> AgentKey | None:
        result = await self._session.execute(
            select(AgentKey).where(AgentKey.key_hash == key_hash)
        )
        return result.scalar_one_or_none()

    async def get_key(self, key_id: int) -> AgentKey | None:
        return await self._session.get(AgentKey, key_id)

    async def list_keys(self, agent_slug: str) -> list[AgentKey]:
        result = await self._session.execute(
            select(AgentKey)
            .where(AgentKey.agent_slug == agent_slug)
            .order_by(AgentKey.created_at.desc())
        )
        return list(result.scalars())

    async def save_key(self, key: AgentKey) -> None:
        self._session.add(key)
        await self._session.commit()
