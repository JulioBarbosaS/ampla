"""Scheduler engine (Epic 08 · 8.1/8.2/8.4) against REAL SQLite + a fake
connection manager: a due schedule is claimed (next_run re-anchored) and fired
to an online agent, and is suppressed by offline / kill-switch / pause."""

from datetime import timedelta

import pytest_asyncio

from app.core.db import build_engine, build_session_factory, create_tables
from app.models.agent import Agent
from app.models.schedule import AgentSchedule
from app.models.user import User, utcnow
from app.repositories.agent_repo import AgentRepository
from app.repositories.hub_state_repo import HubStateRepository
from app.repositories.schedule_repo import ScheduleRepository
from app.repositories.user_repo import UserRepository
from app.services.scheduler_engine import SchedulerEngine
from tests.conftest import make_settings


class FakeManager:
    def __init__(self, *online: str) -> None:
        self._online = set(online)
        self.sent: list[tuple[str, dict]] = []

    def is_online(self, slug: str) -> bool:
        return slug in self._online

    async def send_to_agent(self, slug: str, frame: dict) -> bool:
        self.sent.append((slug, frame))
        return slug in self._online


@pytest_asyncio.fixture
async def setup():
    engine = build_engine("sqlite+aiosqlite:///:memory:")
    await create_tables(engine)
    factory = build_session_factory(engine)
    async with factory() as s:
        owner = await UserRepository(s).add(User(email="o@amp.local", name="O", password_hash="x"))
        await AgentRepository(s).add(
            Agent(slug="backend-julio", user_id=owner.id, display_name="B")
        )
        await HubStateRepository(s).get()  # seed the kill-switch row
        owner_id = owner.id
    yield factory, owner_id
    await engine.dispose()


async def _add_due(factory, owner_id, **over) -> int:
    data = dict(
        owner_id=owner_id,
        agent_slug="backend-julio",
        name="standup",
        kind="interval",
        spec="300",
        prompt="poste o status",
        tools="read",
        enabled=True,
        next_run_at=utcnow() - timedelta(seconds=1),
        created_by=f"user:{owner_id}",
    )
    data.update(over)
    async with factory() as s:
        return (await ScheduleRepository(s).add(AgentSchedule(**data))).id


async def _get(factory, sid: int) -> AgentSchedule:
    async with factory() as s:
        return await ScheduleRepository(s).get(sid)


async def test_due_schedule_fires_to_online_agent(setup):
    factory, owner_id = setup
    sid = await _add_due(factory, owner_id)
    manager = FakeManager("backend-julio")
    now = utcnow()
    await SchedulerEngine(factory, manager, make_settings()).tick(now)
    s = await _get(factory, sid)
    assert s.last_status == "running"
    assert s.next_run_at is not None and s.next_run_at > now  # re-anchored ahead
    assert manager.sent and manager.sent[0][1]["type"] == "scheduled_task"
    assert manager.sent[0][1]["schedule_id"] == sid


async def test_offline_agent_is_skipped(setup):
    factory, owner_id = setup
    sid = await _add_due(factory, owner_id)
    manager = FakeManager()  # nobody online
    await SchedulerEngine(factory, manager, make_settings()).tick(utcnow())
    s = await _get(factory, sid)
    assert s.last_status == "skipped_offline"
    assert manager.sent == []


async def test_kill_switch_suppresses(setup):
    factory, owner_id = setup
    sid = await _add_due(factory, owner_id)
    async with factory() as sess:
        await HubStateRepository(sess).set_auto_responder_enabled(False)
    manager = FakeManager("backend-julio")
    await SchedulerEngine(factory, manager, make_settings()).tick(utcnow())
    s = await _get(factory, sid)
    assert s.last_status == "skipped_killswitch"
    assert manager.sent == []


async def test_paused_agent_is_skipped(setup):
    factory, owner_id = setup
    async with factory() as s:
        agent = await AgentRepository(s).get("backend-julio")
        agent.auto_paused = True
        await s.commit()
    sid = await _add_due(factory, owner_id)
    manager = FakeManager("backend-julio")
    await SchedulerEngine(factory, manager, make_settings()).tick(utcnow())
    assert (await _get(factory, sid)).last_status == "skipped_paused"


async def test_once_schedule_disarms_after_firing(setup):
    factory, owner_id = setup
    past = (utcnow() - timedelta(minutes=5)).isoformat()
    sid = await _add_due(factory, owner_id, kind="once", spec=past)
    manager = FakeManager("backend-julio")
    await SchedulerEngine(factory, manager, make_settings()).tick(utcnow())
    s = await _get(factory, sid)
    assert s.last_status == "running"
    assert s.next_run_at is None  # a past 'once' has no next occurrence
