from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.delegation import Delegation


class DelegationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, delegation: Delegation) -> Delegation:
        self._session.add(delegation)
        await self._session.commit()
        await self._session.refresh(delegation)
        return delegation

    async def save(self, delegation: Delegation) -> None:
        self._session.add(delegation)
        await self._session.commit()

    async def count_open_from(self, from_agent: str) -> int:
        """Open delegations the agent currently has outstanding (defensive cap)."""
        stmt = select(Delegation).where(
            Delegation.from_agent == from_agent, Delegation.status == "open"
        )
        return len(list((await self._session.execute(stmt)).scalars()))

    async def find_open_for_reply(
        self, *, delegator: str, delegate: str, root_message_id: int
    ) -> Delegation | None:
        """The open delegation a reply from `delegate` back to `delegator` in the
        delegated thread would complete. Matched by the task message's id."""
        stmt = select(Delegation).where(
            Delegation.from_agent == delegator,
            Delegation.to_agent == delegate,
            Delegation.root_message_id == root_message_id,
            Delegation.status == "open",
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def list_for_agent(self, agent_slug: str, *, limit: int = 50) -> list[Delegation]:
        """Delegations the agent is involved in, either side (sent or received)."""
        stmt = (
            select(Delegation)
            .where(or_(Delegation.from_agent == agent_slug, Delegation.to_agent == agent_slug))
            .order_by(Delegation.created_at.desc(), Delegation.id.desc())
            .limit(limit)
        )
        return list((await self._session.execute(stmt)).scalars())
