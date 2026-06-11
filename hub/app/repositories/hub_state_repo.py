from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hub_state import HubState

# The singleton row id. There is only ever one hub_state row.
_STATE_ID = 1


class HubStateRepository:
    """Reads/writes the single instance-wide state row, creating it on first use."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self) -> HubState:
        state = await self._session.get(HubState, _STATE_ID)
        if state is None:
            # Lazily seed the singleton with the safe default (auto-respond on).
            # Seeded at startup (lifespan), so requests never race on the insert.
            state = HubState(id=_STATE_ID, auto_responder_enabled=True)
            self._session.add(state)
            await self._session.commit()
            await self._session.refresh(state)
        return state

    async def set_auto_responder_enabled(self, enabled: bool) -> HubState:
        state = await self.get()
        state.auto_responder_enabled = enabled
        self._session.add(state)
        await self._session.commit()
        await self._session.refresh(state)
        return state
