from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import PasswordReset, User, UserAvatar, utcnow


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def count(self) -> int:
        result = await self._session.execute(select(func.count(User.id)))
        return result.scalar_one()

    async def count_admins(self) -> int:
        result = await self._session.execute(
            select(func.count(User.id)).where(User.role == "admin")
        )
        return result.scalar_one()

    async def list_all(self) -> list[User]:
        result = await self._session.execute(select(User).order_by(User.id))
        return list(result.scalars())

    async def get_by_id(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def add(self, user: User) -> User:
        self._session.add(user)
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def save(self, user: User) -> None:
        self._session.add(user)
        await self._session.commit()

    # ---- avatars (stored separately from the hot users row) ----

    async def get_avatar(self, user_id: int) -> UserAvatar | None:
        return await self._session.get(UserAvatar, user_id)

    async def set_avatar(self, user_id: int, data: bytes, mime: str = "image/jpeg") -> None:
        avatar = await self._session.get(UserAvatar, user_id)
        if avatar is None:
            self._session.add(
                UserAvatar(user_id=user_id, data=data, mime=mime, updated_at=utcnow())
            )
        else:
            avatar.data = data
            avatar.mime = mime
            avatar.updated_at = utcnow()
        await self._session.commit()

    async def delete_avatar(self, user_id: int) -> bool:
        avatar = await self._session.get(UserAvatar, user_id)
        if avatar is None:
            return False
        await self._session.delete(avatar)
        await self._session.commit()
        return True

    # ---- password resets ----

    async def add_reset(self, reset: PasswordReset) -> PasswordReset:
        self._session.add(reset)
        await self._session.commit()
        await self._session.refresh(reset)
        return reset

    async def get_reset_by_hash(self, token_hash: str) -> PasswordReset | None:
        result = await self._session.execute(
            select(PasswordReset).where(PasswordReset.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def save_reset(self, reset: PasswordReset) -> None:
        self._session.add(reset)
        await self._session.commit()

    async def invalidate_resets_for(self, user_id: int) -> None:
        """Mark every still-unused password-reset for a user as used, so only the
        newest issued token is ever valid and a completed reset retires all other
        outstanding reset paths (single active reset)."""
        await self._session.execute(
            PasswordReset.__table__.update()
            .where(PasswordReset.user_id == user_id, PasswordReset.used_at.is_(None))
            .values(used_at=utcnow())
        )
        await self._session.commit()
