from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.group import Group, GroupMember


class GroupRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, slug: str) -> Group | None:
        return await self._session.get(Group, slug)

    async def list_all(self) -> list[Group]:
        result = await self._session.execute(select(Group).order_by(Group.slug))
        return list(result.scalars())

    async def add(self, group: Group) -> Group:
        self._session.add(group)
        await self._session.commit()
        await self._session.refresh(group)
        return group

    async def remove(self, group: Group) -> None:
        await self._session.execute(delete(GroupMember).where(GroupMember.group_slug == group.slug))
        await self._session.delete(group)
        await self._session.commit()

    # ---- membros ----

    async def members_of(self, group_slug: str) -> list[str]:
        result = await self._session.execute(
            select(GroupMember.agent_slug)
            .where(GroupMember.group_slug == group_slug)
            .order_by(GroupMember.agent_slug)
        )
        return list(result.scalars())

    async def is_member(self, group_slug: str, agent_slug: str) -> bool:
        return (await self._session.get(GroupMember, (group_slug, agent_slug))) is not None

    async def add_member(self, group_slug: str, agent_slug: str) -> None:
        self._session.add(GroupMember(group_slug=group_slug, agent_slug=agent_slug))
        await self._session.commit()

    async def remove_member(self, group_slug: str, agent_slug: str) -> None:
        await self._session.execute(
            delete(GroupMember).where(
                GroupMember.group_slug == group_slug,
                GroupMember.agent_slug == agent_slug,
            )
        )
        await self._session.commit()
