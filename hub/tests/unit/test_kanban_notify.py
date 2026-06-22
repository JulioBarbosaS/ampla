"""Inbox integration (Epic 06 · 6.5): a comment notifies the card's assignee +
board owner (and @mentions the mentioned agent's owner); assignment and moves
notify the assignee. The actor is never notified of their own action; a muted
thread is suppressed."""

from app.models.agent import Agent
from app.models.kanban import KanbanCard
from app.models.user import User
from app.schemas.kanban import BoardCreate, CardCreate, CardUpdate, CommentCreate
from app.services.kanban_service import KanbanService
from app.services.notification_service import NotificationService
from tests.unit.fakes import (
    FakeAgentRepository,
    FakeAuditRepository,
    FakeKanbanRepository,
    FakeNotificationRepository,
    FakeUserRepository,
)


async def _setup():
    boards = FakeKanbanRepository()
    notifs_repo = FakeNotificationRepository()
    users = FakeUserRepository()
    agents = FakeAgentRepository()
    owner = await users.add(User(email="owner@amp.local", name="Owner", password_hash="x"))
    ana_owner = await users.add(User(email="ana@amp.local", name="AnaOwner", password_hash="x"))
    await agents.add(Agent(slug="backend-ana", user_id=ana_owner.id, display_name="Ana"))
    notifications = NotificationService(notifications=notifs_repo, users=users)
    svc = KanbanService(
        boards=boards, audit=FakeAuditRepository(), agents=agents, notifications=notifications
    )
    return svc, boards, notifs_repo, users, owner, ana_owner


def _for(notifs_repo, user_id):
    return [n for n in notifs_repo._items.values() if n.user_id == user_id]


class TestCommentNotifications:
    async def test_comment_notifies_assignee_owner_and_board_owner(self):
        svc, _b, notifs, _u, owner, ana_owner = await _setup()
        ana_owner.notify_level = "all"  # participating is low-signal — opted in
        board = await svc.create_board(owner, BoardCreate(name="B"))
        card = await svc.create_card(owner, board.id, CardCreate(title="t", assignee="backend-ana"))
        notifs._items.clear()  # drop the assignment notification; isolate the comment
        await svc.add_comment(owner, card.id, CommentCreate(body="Preciso da spec"))
        # the assignee's owner is notified (participating); the commenter (owner,
        # also the board owner) is NOT notified of their own comment
        ana = _for(notifs, ana_owner.id)
        assert len(ana) == 1 and ana[0].reason == "participating"
        assert _for(notifs, owner.id) == []

    async def test_mention_notifies_the_mentioned_agents_owner(self):
        svc, _b, notifs, _u, owner, ana_owner = await _setup()
        board = await svc.create_board(owner, BoardCreate(name="B"))
        card = await svc.create_card(owner, board.id, CardCreate(title="t"))
        await svc.add_comment(owner, card.id, CommentCreate(body="@backend-ana pode revisar?"))
        ana = _for(notifs, ana_owner.id)
        assert len(ana) == 1 and ana[0].reason == "mention"  # mention outranks participating

    async def test_commenter_not_notified_of_own_comment(self):
        svc, _b, notifs, _u, owner, _ana = await _setup()
        board = await svc.create_board(owner, BoardCreate(name="B"))
        # card assigned to the owner themselves; the owner comments
        card = await svc.create_card(
            owner, board.id, CardCreate(title="t", assignee=f"user:{owner.id}")
        )
        notifs._items.clear()
        await svc.add_comment(owner, card.id, CommentCreate(body="nota minha"))
        assert _for(notifs, owner.id) == []

    async def test_muted_thread_suppresses_the_comment(self):
        svc, _b, notifs, _u, owner, ana_owner = await _setup()
        ana_owner.notify_level = "all"  # so only the per-thread mute can suppress it
        board = await svc.create_board(owner, BoardCreate(name="B"))
        card = await svc.create_card(owner, board.id, CardCreate(title="t", assignee="backend-ana"))
        notifs._items.clear()
        await notifs.upsert_subscription(ana_owner.id, f"kanban:card:{card.id}", "ignored")
        await svc.add_comment(owner, card.id, CommentCreate(body="oi"))
        assert _for(notifs, ana_owner.id) == []  # participating is gated by the mute


class TestAssignmentNotifications:
    async def test_create_with_assignee_notifies_the_assignees_owner(self):
        svc, _b, notifs, _u, owner, ana_owner = await _setup()
        board = await svc.create_board(owner, BoardCreate(name="B"))
        await svc.create_card(owner, board.id, CardCreate(title="t", assignee="backend-ana"))
        ana = _for(notifs, ana_owner.id)
        assert len(ana) == 1 and ana[0].reason == "task_assigned"

    async def test_self_assignment_does_not_notify(self):
        svc, _b, notifs, _u, owner, _ana = await _setup()
        board = await svc.create_board(owner, BoardCreate(name="B"))
        await svc.create_card(owner, board.id, CardCreate(title="t", assignee=f"user:{owner.id}"))
        assert _for(notifs, owner.id) == []

    async def test_update_assigning_notifies(self):
        svc, _b, notifs, _u, owner, ana_owner = await _setup()
        board = await svc.create_board(owner, BoardCreate(name="B"))
        card = await svc.create_card(owner, board.id, CardCreate(title="t"))
        await svc.update_card(owner, card.id, CardUpdate(assignee="backend-ana"))
        ana = _for(notifs, ana_owner.id)
        assert len(ana) == 1 and ana[0].reason == "task_assigned"


class TestMoveNotifications:
    async def test_move_notifies_the_assignee_excluding_the_mover(self):
        svc, boards, notifs, _u, owner, ana_owner = await _setup()
        ana_owner.notify_level = "all"  # state_change is low-signal — opted in
        board = await svc.create_board(owner, BoardCreate(name="B"))
        _, columns, _ = await svc.get_board_full(owner, board.id)
        landing = next(c for c in columns if c.is_landing)
        other = next(c for c in columns if not c.is_landing)
        # seed the card directly (bypass create_card's assignment notification)
        card = await boards.add_card(
            KanbanCard(
                board_id=board.id,
                column_id=landing.id,
                rank="m",
                title="t",
                created_by=f"user:{owner.id}",
                assignee="backend-ana",
            )
        )
        await svc.move_card(
            owner, card.id, other.id, before_id=None, after_id=None, expected_version=card.version
        )
        ana = _for(notifs, ana_owner.id)
        assert len(ana) == 1 and ana[0].reason == "state_change"
