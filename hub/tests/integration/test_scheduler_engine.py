"""Scheduler engine (Epic 08 · 8.1/8.2/8.4) against REAL SQLite + a fake
connection manager: a due schedule is claimed (next_run re-anchored) and fired
to an online agent, and is suppressed by offline / kill-switch / pause."""

from datetime import timedelta

import pytest_asyncio

from app.core.db import build_engine, build_session_factory, create_tables
from app.models.agent import Agent
from app.models.notification import Notification
from app.models.schedule import AgentSchedule
from app.models.user import User, utcnow
from app.repositories.agent_repo import AgentRepository
from app.repositories.audit_repo import AuditRepository
from app.repositories.hub_state_repo import HubStateRepository
from app.repositories.notification_repo import NotificationRepository
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


class RaisingManager:
    """Online, but dispatch blows up — to exercise the per-job failure path."""

    def is_online(self, slug: str) -> bool:
        return True

    async def send_to_agent(self, slug: str, frame: dict) -> bool:
        raise RuntimeError("boom")


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


async def test_failing_fire_is_recorded_failed_without_aborting_the_tick(setup):
    # A job that throws is recorded `failed` and never aborts the loop — the
    # other due schedules in the same tick still run (spec 8.1).
    factory, owner_id = setup
    sid1 = await _add_due(factory, owner_id, name="a")
    sid2 = await _add_due(factory, owner_id, name="b")
    await SchedulerEngine(factory, RaisingManager(), make_settings()).tick(utcnow())
    assert (await _get(factory, sid1)).last_status == "failed"
    assert (await _get(factory, sid2)).last_status == "failed"  # 2nd still processed
    async with factory() as s:
        events = [e.event for e in await AuditRepository(s).list_recent(50)]
    assert events.count("scheduled_task_fired") == 2  # both fires audited


async def test_notification_prune_is_audited(setup):
    # The retention sweep deletes rows — an auditable mutation (spec 8.2).
    factory, owner_id = setup
    async with factory() as s:
        old = utcnow() - timedelta(days=400)
        await NotificationRepository(s).add(
            Notification(
                user_id=owner_id,
                subject_type="dm",
                subject_key="dm:a:b",
                reason="direct_message",
                title="velha",
                status="done",
                created_at=old,
                updated_at=old,
            )
        )
    await SchedulerEngine(factory, FakeManager(), make_settings()).tick(utcnow())
    async with factory() as s:
        events = [e.event for e in await AuditRepository(s).list_recent(50)]
    assert "notifications_pruned" in events
