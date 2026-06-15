"""Guardrail presets (Epic 04 · 4.1): seed built-ins, CRUD authz, and apply
copies the preset's settings onto an owned agent."""

import pytest

from app.models.agent import Agent
from app.models.user import User
from app.schemas.preset import PresetCreate, PresetSettings, PresetUpdate
from app.services.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.services.preset_service import PresetService
from tests.unit.fakes import (
    FakeAgentRepository,
    FakeAuditRepository,
    FakeGuardrailPresetRepository,
)


def make_user(uid: int, role: str = "member") -> User:
    u = User(email=f"u{uid}@amp.local", name=f"U{uid}", password_hash="x")
    u.id = uid
    u.role = role
    return u


async def _setup():
    presets = FakeGuardrailPresetRepository()
    agents = FakeAgentRepository()
    audit = FakeAuditRepository()
    svc = PresetService(presets, agents, audit)
    return svc, presets, agents, audit


class TestBuiltins:
    async def test_ensure_builtins_is_idempotent(self):
        svc, _p, _a, _au = await _setup()
        assert await svc.ensure_builtins() == 4
        assert await svc.ensure_builtins() == 0  # second run seeds nothing
        names = [p.name for p in await svc.list(make_user(1))]
        assert "Estrito (padrão)" in names and "Confiável (perigo)" in names


class TestCrud:
    async def test_create_and_list_includes_builtins_and_own(self):
        svc, _p, _a, _au = await _setup()
        await svc.ensure_builtins()
        owner = make_user(1)
        await svc.create(owner, PresetCreate(name="Meu", settings=PresetSettings(mode="auto")))
        visible = await svc.list(owner)
        assert "Meu" in [p.name for p in visible]
        # another user does not see this personal preset
        other = [p.name for p in await svc.list(make_user(2))]
        assert "Meu" not in other

    async def test_duplicate_name_per_owner_conflicts(self):
        svc, _p, _a, _au = await _setup()
        owner = make_user(1)
        await svc.create(owner, PresetCreate(name="Meu", settings=PresetSettings()))
        with pytest.raises(ConflictError):
            await svc.create(owner, PresetCreate(name="Meu", settings=PresetSettings()))

    async def test_member_cannot_edit_a_builtin(self):
        svc, _p, _a, _au = await _setup()
        await svc.ensure_builtins()
        builtin = (await svc.list(make_user(1)))[0]  # built-ins first
        assert builtin.owner_id is None
        with pytest.raises(PermissionDeniedError):
            await svc.update(make_user(1), builtin.id, PresetUpdate(name="Hack"))

    async def test_member_cannot_edit_another_users_preset(self):
        svc, _p, _a, _au = await _setup()
        mine = await svc.create(make_user(1), PresetCreate(name="A", settings=PresetSettings()))
        with pytest.raises(PermissionDeniedError):
            await svc.update(make_user(2), mine.id, PresetUpdate(name="B"))


class TestApply:
    async def test_apply_copies_settings_onto_the_agent(self):
        svc, _p, agents, audit = await _setup()
        owner = make_user(1)
        await agents.add(Agent(slug="backend-julio", user_id=owner.id, display_name="B"))
        preset = await svc.create(
            owner,
            PresetCreate(
                name="Escrita",
                settings=PresetSettings(mode="auto", allow_write=True, confine_to_dir=False),
            ),
        )
        agent = await svc.apply(owner, "backend-julio", preset.id)
        assert agent.mode == "auto"
        assert agent.allow_write is True
        assert agent.confine_to_dir is False
        assert audit.has("preset_applied")

    async def test_apply_a_builtin(self):
        svc, _p, agents, _au = await _setup()
        await svc.ensure_builtins()
        owner = make_user(1)
        await agents.add(Agent(slug="backend-julio", user_id=owner.id, display_name="B"))
        confiavel = next(p for p in await svc.list(owner) if p.name == "Confiável (perigo)")
        agent = await svc.apply(owner, "backend-julio", confiavel.id)
        assert agent.allow_write is True and agent.block_sensitive_paths is False

    async def test_cannot_apply_to_an_unowned_agent(self):
        svc, _p, agents, _au = await _setup()
        await agents.add(Agent(slug="backend-julio", user_id=1, display_name="B"))
        preset = await svc.create(make_user(2), PresetCreate(name="X", settings=PresetSettings()))
        with pytest.raises(PermissionDeniedError):
            await svc.apply(make_user(2), "backend-julio", preset.id)

    async def test_apply_unknown_preset_is_not_found(self):
        svc, _p, agents, _au = await _setup()
        await agents.add(Agent(slug="backend-julio", user_id=1, display_name="B"))
        with pytest.raises(NotFoundError):
            await svc.apply(make_user(1), "backend-julio", 999)
