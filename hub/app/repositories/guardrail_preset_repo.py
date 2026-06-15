from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.guardrail_preset import GuardrailPreset


class GuardrailPresetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, preset: GuardrailPreset) -> GuardrailPreset:
        self._session.add(preset)
        await self._session.commit()
        await self._session.refresh(preset)
        return preset

    async def save(self, preset: GuardrailPreset) -> None:
        self._session.add(preset)
        await self._session.commit()

    async def delete(self, preset: GuardrailPreset) -> None:
        await self._session.delete(preset)
        await self._session.commit()

    async def get(self, preset_id: int) -> GuardrailPreset | None:
        return await self._session.get(GuardrailPreset, preset_id)

    async def get_builtin_by_name(self, name: str) -> GuardrailPreset | None:
        result = await self._session.execute(
            select(GuardrailPreset).where(
                GuardrailPreset.owner_id.is_(None), GuardrailPreset.name == name
            )
        )
        return result.scalar_one_or_none()

    async def get_by_owner_name(self, owner_id: int, name: str) -> GuardrailPreset | None:
        result = await self._session.execute(
            select(GuardrailPreset).where(
                GuardrailPreset.owner_id == owner_id, GuardrailPreset.name == name
            )
        )
        return result.scalar_one_or_none()

    async def list_visible(self, owner_id: int) -> list[GuardrailPreset]:
        """Built-ins (owner_id null) + the user's own, built-ins first by name."""
        result = await self._session.execute(
            select(GuardrailPreset)
            .where(or_(GuardrailPreset.owner_id.is_(None), GuardrailPreset.owner_id == owner_id))
            .order_by(GuardrailPreset.owner_id.is_(None).desc(), GuardrailPreset.name)
        )
        return list(result.scalars())
