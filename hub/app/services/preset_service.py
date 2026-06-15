"""Reusable guardrail presets (Epic 04 · 4.1). v1: apply-and-detach — applying a
preset COPIES its settings onto the agent (no live link).

Authorization: a user sees built-ins (owner_id null) + their own; only the owner
(or an admin) may edit/delete a preset; built-ins are admin-only to mutate."""

import logging

from app.models.agent import Agent
from app.models.guardrail_preset import GuardrailPreset
from app.models.user import User
from app.repositories.agent_repo import AgentRepository
from app.repositories.audit_repo import AuditRepository
from app.repositories.guardrail_preset_repo import GuardrailPresetRepository
from app.schemas.preset import BUILTIN_PRESETS, PresetCreate, PresetSettings, PresetUpdate
from app.services.errors import ConflictError, NotFoundError, PermissionDeniedError

logger = logging.getLogger(__name__)


class PresetService:
    def __init__(
        self,
        presets: GuardrailPresetRepository,
        agents: AgentRepository,
        audit: AuditRepository,
    ) -> None:
        self._presets = presets
        self._agents = agents
        self._audit = audit

    async def ensure_builtins(self) -> int:
        """Seed the built-in presets once (idempotent — by name). Returns count
        created. Run best-effort at startup."""
        created = 0
        for name, settings in BUILTIN_PRESETS:
            if await self._presets.get_builtin_by_name(name) is None:
                await self._presets.add(
                    GuardrailPreset(owner_id=None, name=name, settings=settings)
                )
                created += 1
        return created

    async def list(self, user: User) -> list[GuardrailPreset]:
        return await self._presets.list_visible(user.id)

    async def create(self, user: User, data: PresetCreate) -> GuardrailPreset:
        if await self._presets.get_by_owner_name(user.id, data.name) is not None:
            raise ConflictError("Você já tem um preset com este nome.")
        return await self._presets.add(
            GuardrailPreset(owner_id=user.id, name=data.name, settings=data.settings.model_dump())
        )

    async def _mutable(self, user: User, preset_id: int) -> GuardrailPreset:
        preset = await self._presets.get(preset_id)
        if preset is None:
            raise NotFoundError("Preset não encontrado.")
        # Built-ins (owner_id null) are admin-only; personal presets need ownership.
        if user.role == "admin":
            return preset
        if preset.owner_id != user.id:
            raise PermissionDeniedError("Você não gerencia este preset.")
        return preset

    async def update(self, user: User, preset_id: int, data: PresetUpdate) -> GuardrailPreset:
        preset = await self._mutable(user, preset_id)
        if data.name is not None and data.name != preset.name:
            owner = preset.owner_id
            clash = (
                await self._presets.get_by_owner_name(owner, data.name)
                if owner is not None
                else await self._presets.get_builtin_by_name(data.name)
            )
            if clash is not None:
                raise ConflictError("Já existe um preset com este nome.")
            preset.name = data.name
        if data.settings is not None:
            preset.settings = data.settings.model_dump()
        await self._presets.save(preset)
        return preset

    async def delete(self, user: User, preset_id: int) -> None:
        preset = await self._mutable(user, preset_id)
        await self._presets.delete(preset)

    async def apply(self, user: User, slug: str, preset_id: int) -> Agent:
        """Copies a (readable) preset's settings onto an owned agent. Audited —
        applying a permissive preset is a privileged action."""
        preset = await self._presets.get(preset_id)
        # Readable = built-in or own (admins read all). A non-readable id is hidden.
        if preset is None or (
            preset.owner_id is not None and preset.owner_id != user.id and user.role != "admin"
        ):
            raise NotFoundError("Preset não encontrado.")
        agent = await self._agents.get(slug)
        if agent is None:
            raise NotFoundError("Agente não encontrado.")
        if agent.user_id != user.id and user.role != "admin":
            raise PermissionDeniedError("Você não gerencia este agente.")

        settings = PresetSettings.model_validate(preset.settings)
        for field, value in settings.model_dump().items():
            setattr(agent, field, value)
        await self._agents.save(agent)
        await self._audit.record(
            "preset_applied",
            actor=user.email,
            detail={"slug": slug, "preset_id": preset_id, "name": preset.name},
        )
        return agent
