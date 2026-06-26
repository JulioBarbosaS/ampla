from datetime import datetime

from sqlalchemy import func, select
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

    async def aggregate(self, since: datetime) -> dict:
        """Windowed roll-up of runs for the instance metrics panel: totals + the
        result breakdown (the cost/security story over the window)."""
        totals = (
            await self._session.execute(
                select(
                    func.count(AutorespondRun.id),
                    func.coalesce(func.sum(AutorespondRun.cost_usd), 0.0),
                    func.coalesce(func.sum(AutorespondRun.output_tokens), 0),
                    func.coalesce(func.sum(AutorespondRun.input_tokens), 0),
                    func.coalesce(func.avg(AutorespondRun.duration_ms), 0.0),
                ).where(AutorespondRun.created_at >= since)
            )
        ).one()
        timed_out = (
            await self._session.execute(
                select(func.count(AutorespondRun.id)).where(
                    AutorespondRun.created_at >= since, AutorespondRun.timed_out.is_(True)
                )
            )
        ).scalar_one()
        by_result_rows = await self._session.execute(
            select(AutorespondRun.result, func.count(AutorespondRun.id))
            .where(AutorespondRun.created_at >= since)
            .group_by(AutorespondRun.result)
        )
        return {
            "total_runs": totals[0],
            "total_cost_usd": round(float(totals[1]), 6),
            "total_output_tokens": int(totals[2]),
            "total_input_tokens": int(totals[3]),
            "avg_duration_ms": int(totals[4]),
            "timed_out": timed_out,
            "by_result": {result: count for result, count in by_result_rows},
        }

    async def daily_series(self, since: datetime) -> list[dict]:
        """Per-day runs + cost over the window (the time-series chart). SQLite's
        date() parses the stored ISO timestamps."""
        day = func.date(AutorespondRun.created_at)
        rows = await self._session.execute(
            select(
                day,
                func.count(AutorespondRun.id),
                func.coalesce(func.sum(AutorespondRun.cost_usd), 0.0),
            )
            .where(AutorespondRun.created_at >= since)
            .group_by(day)
            .order_by(day)
        )
        return [
            {"date": str(date), "runs": runs, "cost_usd": round(float(cost), 6)}
            for date, runs, cost in rows
        ]
