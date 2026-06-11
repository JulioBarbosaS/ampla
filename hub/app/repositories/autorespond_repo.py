from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.autorespond_run import AutorespondRun


class AutorespondRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, run: AutorespondRun) -> AutorespondRun:
        self._session.add(run)
        await self._session.commit()
        await self._session.refresh(run)
        return run

    async def list_for_agent(self, agent_slug: str, limit: int) -> list[AutorespondRun]:
        result = await self._session.execute(
            select(AutorespondRun)
            .where(AutorespondRun.agent_slug == agent_slug)
            .order_by(AutorespondRun.created_at.desc(), AutorespondRun.id.desc())
            .limit(limit)
        )
        return list(result.scalars())

    async def list_all(self, limit: int) -> list[AutorespondRun]:
        result = await self._session.execute(
            select(AutorespondRun)
            .order_by(AutorespondRun.created_at.desc(), AutorespondRun.id.desc())
            .limit(limit)
        )
        return list(result.scalars())
