from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, event: str, actor: str = "", detail: dict | None = None) -> None:
        self._session.add(AuditLog(event=event, actor=actor, detail=detail))
        await self._session.commit()

    async def list_recent(self, limit: int = 100) -> list[AuditLog]:
        result = await self._session.execute(
            select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit)
        )
        return list(result.scalars())
