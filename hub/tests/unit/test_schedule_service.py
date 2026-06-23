"""Scheduled agent tasks (Epic 08 · 8.3): ownership authz, (kind, spec)
validation + the interval floor, and next_run_at bookkeeping."""

import pytest

from app.models.agent import Agent
from app.models.user import User
from app.schemas.schedule import ScheduleCreate, ScheduleUpdate
from app.services.errors import InvalidInputError, NotFoundError, PermissionDeniedError
from app.services.schedule_service import ScheduleService
from tests.unit.fakes import (
    FakeAgentRepository,
    FakeAuditRepository,
    FakeScheduleRepository,
)


async def _service():
    agents = FakeAgentRepository()
    schedules = FakeScheduleRepository()
    audit = FakeAuditRepository()
    owner = User(email="o@amp.local", name="O", password_hash="x")
    owner.id = 1
    other = User(email="x@amp.local", name="X", password_hash="x")
    other.id = 2
    await agents.add(Agent(slug="backend-julio", user_id=1, display_name="B"))
    svc = ScheduleService(schedules, agents, audit, min_interval_secs=60)
    return svc, owner, other, audit


def _create(**over) -> ScheduleCreate:
    data = {"name": "Standup", "kind": "interval", "spec": "300", "prompt": "poste o status"}
    data.update(over)
    return ScheduleCreate(**data)


class TestCreate:
    async def test_creates_and_arms_next_run(self):
        svc, owner, _, audit = await _service()
        s = await svc.create(owner, "backend-julio", _create())
        assert s.id is not None and s.owner_id == 1
        assert s.created_by == "user:1"
        assert s.next_run_at is not None  # armed
        assert audit.has("schedule_created")

    async def test_disabled_schedule_is_not_armed(self):
        svc, owner, _, _ = await _service()
        s = await svc.create(owner, "backend-julio", _create(enabled=False))
        assert s.next_run_at is None

    async def test_cannot_schedule_another_users_agent(self):
        svc, _, other, _ = await _service()
        with pytest.raises(PermissionDeniedError):
            await svc.create(other, "backend-julio", _create())

    async def test_unknown_agent_is_404(self):
        svc, owner, _, _ = await _service()
        with pytest.raises(NotFoundError):
            await svc.create(owner, "ghost", _create())

    async def test_interval_below_floor_rejected(self):
        svc, owner, _, _ = await _service()
        with pytest.raises(InvalidInputError):
            await svc.create(owner, "backend-julio", _create(spec="30"))

    async def test_bad_cron_rejected(self):
        svc, owner, _, _ = await _service()
        with pytest.raises(InvalidInputError):
            await svc.create(owner, "backend-julio", _create(kind="cron", spec="bogus"))


class TestUpdateDelete:
    async def test_disabling_clears_next_run(self):
        svc, owner, _, _ = await _service()
        s = await svc.create(owner, "backend-julio", _create())
        updated = await svc.update(owner, s.id, ScheduleUpdate(enabled=False))
        assert updated.enabled is False and updated.next_run_at is None
        rearmed = await svc.update(owner, s.id, ScheduleUpdate(enabled=True))
        assert rearmed.next_run_at is not None

    async def test_changing_spec_revalidates(self):
        svc, owner, _, _ = await _service()
        s = await svc.create(owner, "backend-julio", _create())
        with pytest.raises(InvalidInputError):
            await svc.update(owner, s.id, ScheduleUpdate(spec="5"))  # below floor

    async def test_non_owner_cannot_touch(self):
        svc, owner, other, _ = await _service()
        s = await svc.create(owner, "backend-julio", _create())
        with pytest.raises(PermissionDeniedError):
            await svc.update(other, s.id, ScheduleUpdate(name="x"))
        with pytest.raises(PermissionDeniedError):
            await svc.delete(other, s.id)

    async def test_run_now_arms_immediately_and_reenables(self):
        svc, owner, _, audit = await _service()
        s = await svc.create(owner, "backend-julio", _create(enabled=False))
        ran = await svc.run_now(owner, s.id)
        assert ran.enabled is True and ran.next_run_at is not None
        assert audit.has("schedule_run_now")

    async def test_delete_removes(self):
        svc, owner, _, _ = await _service()
        s = await svc.create(owner, "backend-julio", _create())
        await svc.delete(owner, s.id)
        with pytest.raises(NotFoundError):
            await svc.get(owner, s.id)
