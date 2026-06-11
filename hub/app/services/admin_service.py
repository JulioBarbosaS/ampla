"""Instance-wide admin controls. Authorization (admin-only) is enforced at the
route via the require_admin dependency; this service assumes a vetted actor."""

from app.models.user import User
from app.repositories.audit_repo import AuditRepository
from app.repositories.hub_state_repo import HubStateRepository


class AdminService:
    def __init__(self, state: HubStateRepository, audit: AuditRepository) -> None:
        self._state = state
        self._audit = audit

    async def get_kill_switch(self) -> bool:
        return (await self._state.get()).auto_responder_enabled

    async def set_kill_switch(self, actor: User, enabled: bool) -> bool:
        """Persists the global flag and audits the toggle (containment is
        security-relevant — who silenced/restored every agent must be on record)."""
        await self._state.set_auto_responder_enabled(enabled)
        await self._audit.record(
            "kill_switch_toggled",
            actor=actor.email,
            detail={"auto_responder_enabled": enabled},
        )
        return enabled
