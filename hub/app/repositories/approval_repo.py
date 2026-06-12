from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import Approval


class ApprovalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, approval: Approval) -> Approval:
        self._session.add(approval)
        await self._session.commit()
        await self._session.refresh(approval)
        return approval

    async def save(self, approval: Approval) -> None:
        self._session.add(approval)
        await self._session.commit()

    async def get(self, approval_id: int) -> Approval | None:
        return await self._session.get(Approval, approval_id)

    async def list_for_agent(
        self, agent_slug: str, *, status: str | None = None, limit: int = 50
    ) -> list[Approval]:
        stmt = select(Approval).where(Approval.agent_slug == agent_slug)
        if status is not None:
            stmt = stmt.where(Approval.status == status)
        stmt = stmt.order_by(Approval.created_at.desc(), Approval.id.desc()).limit(limit)
        return list((await self._session.execute(stmt)).scalars())

    async def list_pending_before(self, cutoff: datetime) -> list[Approval]:
        """Pending approvals older than `cutoff` — fed to the expiry auto-reject."""
        stmt = select(Approval).where(Approval.status == "pending", Approval.created_at < cutoff)
        return list((await self._session.execute(stmt)).scalars())
