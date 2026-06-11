import pytest

from app.core.mentions import parse_mentions
from app.models.user import User
from app.services.errors import NotFoundError
from app.services.notification_service import NotificationService
from tests.unit.fakes import FakeNotificationRepository


def make_user(user_id: int) -> User:
    user = User(email=f"u{user_id}@amp.local", name=f"U{user_id}", password_hash="x")
    user.id = user_id
    user.role = "member"
    return user


@pytest.fixture
def repo() -> FakeNotificationRepository:
    return FakeNotificationRepository()


@pytest.fixture
def service(repo) -> NotificationService:
    return NotificationService(notifications=repo)


async def _notify(service, user_id, subject_key="thread:1", reason="direct_message", **kw):
    return await service.notify(
        user_id,
        subject_type=kw.get("subject_type", "dm"),
        subject_key=subject_key,
        reason=reason,
        title=kw.get("title", "t"),
        actor=kw.get("actor", "mobile-eduardo"),
        agent_slug=kw.get("agent_slug"),
    )


class TestCollapsing:
    async def test_first_event_creates_a_row(self, service, repo):
        await _notify(service, 1)
        assert len(repo._items) == 1

    async def test_second_event_same_subject_collapses(self, service, repo):
        await _notify(service, 1, reason="direct_message")
        first = await service.triage(make_user(1), 1, unread=False)  # read it
        assert first.unread is False
        await _notify(service, 1, reason="direct_message")  # new activity
        assert len(repo._items) == 1  # updated, not inserted
        assert repo._items[1].unread is True  # bumped back to unread

    async def test_reason_precedence_mention_sticks(self, service, repo):
        await _notify(service, 1, reason="participating")
        await _notify(service, 1, reason="mention")
        await _notify(service, 1, reason="direct_message")  # lower priority
        assert repo._items[1].reason == "mention"  # stays the most relevant

    async def test_done_reopens_on_mention_but_not_on_dm(self, service, repo):
        await _notify(service, 1, reason="direct_message")
        await service.triage(make_user(1), 1, status="done")
        # low-signal on a done thread → no resurface
        assert await _notify(service, 1, reason="direct_message") is None
        assert repo._items[1].status == "done"
        # high-signal (mention) re-opens
        await _notify(service, 1, reason="mention")
        assert repo._items[1].status == "inbox"
        assert repo._items[1].unread is True


class TestReadAndIsolation:
    async def test_unread_count_and_mark_read(self, service):
        await _notify(service, 1, subject_key="thread:1")
        await _notify(service, 1, subject_key="thread:2")
        assert await service.unread_count(make_user(1)) == 2
        await service.triage(make_user(1), 1, unread=False)
        assert await service.unread_count(make_user(1)) == 1

    async def test_list_filters_by_status(self, service):
        await _notify(service, 1, subject_key="thread:1")
        await service.triage(make_user(1), 1, status="saved")
        await _notify(service, 1, subject_key="thread:2")
        saved = await service.list(make_user(1), status="saved")
        assert [n.subject_key for n in saved] == ["thread:1"]

    async def test_cross_user_id_is_not_found(self, service):
        await _notify(service, 1)  # belongs to user 1
        with pytest.raises(NotFoundError):
            await service.triage(make_user(2), 1, unread=False)  # user 2 cannot touch it

    async def test_list_only_returns_own(self, service):
        await _notify(service, 1, subject_key="thread:1")
        await _notify(service, 2, subject_key="thread:1")
        assert len(await service.list(make_user(1))) == 1


class TestMentionParser:
    def test_extracts_unique_slugs_in_order(self):
        assert parse_mentions("oi @backend-julio e @mobile-eduardo e de novo @backend-julio") == [
            "backend-julio",
            "mobile-eduardo",
        ]

    def test_ignores_emails_and_invalid(self):
        # uppercase doesn't fit the slug shape after @, so it's ignored
        assert parse_mentions("sem mencao aqui") == []
        assert parse_mentions("@A maiúsculo não casa, @ok-slug casa") == ["ok-slug"]
