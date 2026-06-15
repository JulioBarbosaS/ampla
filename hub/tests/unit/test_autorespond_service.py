import pytest

from app.models.agent import Agent
from app.schemas.ws import AutorespondRecord
from app.services.autorespond_service import (
    MAX_LIMIT,
    AutorespondService,
    escalation_outcome,
)
from app.services.notification_service import NotificationService
from tests.unit.fakes import (
    FakeAgentRepository,
    FakeAutorespondRunRepository,
    FakeNotificationRepository,
    FakeUserRepository,
)


def make_record(**overrides) -> AutorespondRecord:
    base = dict(
        trigger_message_id=1,
        from_sender="mobile-eduardo",
        result="replied",
        reason=None,
        reply_preview="ok",
        tools_allowed="Read,Grep,Glob",
        tools_disallowed="Bash",
        guardrails={"trusted_sender": False, "sandbox": "host"},
        duration_ms=10,
        timed_out=False,
    )
    base.update(overrides)
    return AutorespondRecord(**base)


@pytest.fixture
def repo() -> FakeAutorespondRunRepository:
    return FakeAutorespondRunRepository()


@pytest.fixture
def service(repo) -> AutorespondService:
    return AutorespondService(runs=repo)


class TestAutorespondService:
    async def test_record_run_stores_under_the_authenticated_slug(self, service):
        # the record names another sender, but agent_slug is the authenticated one
        run = await service.record_run("backend-julio", make_record(from_sender="mobile-eduardo"))
        assert run.agent_slug == "backend-julio"
        assert run.from_sender == "mobile-eduardo"
        assert run.result == "replied"

    async def test_list_for_agent_clamps_limit(self, service, repo):
        await service.list_for_agent("backend-julio", limit=10_000)
        assert repo.last_limit == MAX_LIMIT
        await service.list_for_agent("backend-julio", limit=0)
        assert repo.last_limit == 1  # floored to at least 1

    async def test_list_all_clamps_limit(self, service, repo):
        await service.list_all(limit=10_000)
        assert repo.last_limit == MAX_LIMIT


class TestEscalationOutcome:
    """The pure mapping from a reported run to its escalation outcome (4.3)."""

    def test_replied_never_escalates(self):
        assert escalation_outcome(make_record(result="replied")) is None

    def test_benign_skip_never_escalates(self):
        assert escalation_outcome(make_record(result="skipped", reason="mode_inbox")) is None

    def test_failed_and_blocked_are_configurable(self):
        failed = escalation_outcome(make_record(result="failed", reason="timeout"))
        blocked = escalation_outcome(make_record(result="blocked", reason="x"))
        assert failed == ("failed", False)
        assert blocked == ("blocked", False)

    def test_throttle_skips_are_configurable(self):
        for reason in ("rate_limited", "budget_exceeded", "outside_hours"):
            outcome = escalation_outcome(make_record(result="skipped", reason=reason))
            assert outcome == (reason, False)

    def test_sentinel_is_forced(self):
        # the model's __ESCALATE__ reported as a skipped run with reason=escalate
        assert escalation_outcome(make_record(result="skipped", reason="escalate")) == (
            "escalate",
            True,
        )


class TestEscalationGlue:
    """record_run routes the right outcomes to the owner's Inbox (4.3)."""

    async def _service(self):
        runs = FakeAutorespondRunRepository()
        agents = FakeAgentRepository()
        notifications = FakeNotificationRepository()
        users = FakeUserRepository()
        owner = await users.add(make_owner())
        await agents.add(
            Agent(slug="backend-julio", user_id=owner.id, display_name="B")
        )  # escalate_on defaults to ["failed", "blocked"] via the fake
        svc = AutorespondService(
            runs=runs,
            agents=agents,
            notifications=NotificationService(notifications=notifications, users=users),
        )
        return svc, agents, notifications, owner

    async def test_failed_escalates_to_the_owner_inbox(self):
        svc, _agents, notifications, owner = await self._service()
        await svc.record_run("backend-julio", make_record(result="failed", reason="timeout"))
        assert len(notifications._items) == 1
        note = notifications._items[1]
        assert note.user_id == owner.id
        assert note.reason == "escalation"
        assert note.subject_key == "dm:backend-julio:mobile-eduardo"  # collapses on the convo
        assert "msg=1" in note.link

    async def test_outcome_not_opted_in_does_not_escalate(self):
        svc, agents, notifications, _owner = await self._service()
        agent = await agents.get("backend-julio")
        agent.escalate_on = ["failed"]  # owner did NOT opt into rate_limited
        await agents.save(agent)
        await svc.record_run("backend-julio", make_record(result="skipped", reason="rate_limited"))
        assert notifications._items == {}

    async def test_sentinel_escalates_even_when_escalate_on_is_empty(self):
        svc, agents, notifications, _owner = await self._service()
        agent = await agents.get("backend-julio")
        agent.escalate_on = []  # escalation disabled for normal outcomes
        await agents.save(agent)
        await svc.record_run("backend-julio", make_record(result="skipped", reason="escalate"))
        assert len(notifications._items) == 1
        assert notifications._items[1].reason == "escalation"

    async def test_replied_run_does_not_escalate(self):
        svc, _agents, notifications, _owner = await self._service()
        await svc.record_run("backend-julio", make_record(result="replied"))
        assert notifications._items == {}

    async def test_run_is_still_recorded_when_escalation_is_off(self):
        # the run row is the source of truth — it persists regardless of routing
        svc, agents, _notifications, _owner = await self._service()
        agent = await agents.get("backend-julio")
        agent.escalate_on = []
        await agents.save(agent)
        run = await svc.record_run("backend-julio", make_record(result="failed", reason="x"))
        assert run.result == "failed"


def make_owner():
    from app.models.user import User

    return User(email="owner@amp.local", name="Owner", password_hash="x")
