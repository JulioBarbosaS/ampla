import pytest

from app.schemas.ws import AutorespondRecord
from app.services.autorespond_service import MAX_LIMIT, AutorespondService
from tests.unit.fakes import FakeAutorespondRunRepository


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
