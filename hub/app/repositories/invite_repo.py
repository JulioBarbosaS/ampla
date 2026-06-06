from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import Invite


class InviteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, invite: Invite) -> Invite:
        self._session.add(invite)
        await self._session.commit()
        await self._session.refresh(invite)
        return invite

    async def get_by_code(self, code: str) -> Invite | None:
        result = await self._session.execute(select(Invite).where(Invite.code == code))
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Invite]:
        result = await self._session.execute(select(Invite).order_by(Invite.created_at.desc()))
        return list(result.scalars())

    async def save(self, invite: Invite) -> None:
        self._session.add(invite)
        await self._session.commit()
