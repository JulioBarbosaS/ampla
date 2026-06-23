"""Data access for scheduled agent tasks (Epic 08). Pure persistence — the
scheduling algebra lives in app.services.scheduler, authorization in the service.
The engine claims a due schedule by advancing next_run_at in the same write
transaction it reads it, so a slow run can't double-fire on the next tick."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schedule import AgentSchedule


class ScheduleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, schedule: AgentSchedule) -> AgentSchedule:
        self._session.add(schedule)
        await self._session.commit()
        await self._session.refresh(schedule)
        return schedule

    async def get(self, schedule_id: int) -> AgentSchedule | None:
        return await self._session.get(AgentSchedule, schedule_id)

    async def save(self, schedule: AgentSchedule) -> None:
        self._session.add(schedule)
        await self._session.commit()

    async def delete(self, schedule: AgentSchedule) -> None:
        await self._session.delete(schedule)
        await self._session.commit()

    async def list_for_agent(self, agent_slug: str) -> list[AgentSchedule]:
        stmt = (
            select(AgentSchedule)
            .where(AgentSchedule.agent_slug == agent_slug)
            .order_by(AgentSchedule.created_at.desc(), AgentSchedule.id.desc())
        )
        return list((await self._session.execute(stmt)).scalars())

    async def due(self, now: datetime, *, limit: int = 100) -> list[AgentSchedule]:
        """Enabled schedules whose next_run_at has arrived (the engine's tick
        query). A null next_run_at means 'no future occurrence' → never due."""
        stmt = (
            select(AgentSchedule)
            .where(
                AgentSchedule.enabled.is_(True),
                AgentSchedule.next_run_at.is_not(None),
                AgentSchedule.next_run_at <= now,
            )
            .order_by(AgentSchedule.next_run_at)
            .limit(limit)
        )
        return list((await self._session.execute(stmt)).scalars())
