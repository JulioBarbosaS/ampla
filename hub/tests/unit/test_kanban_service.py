"""KanbanService unit tests (Epic 06 · 6.1): CRUD over boards/columns/cards/
comments and the human authorization model, against fake repos."""

import pytest

from app.models.user import User
from app.schemas.kanban import (
    BoardCreate,
    BoardUpdate,
    CardCreate,
    CardUpdate,
    ColumnCreate,
    ColumnUpdate,
    CommentCreate,
)
from app.services.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.services.kanban_service import DEFAULT_COLUMNS, KanbanService
from tests.unit.fakes import FakeAuditRepository, FakeKanbanRepository, FakeUserRepository


async def _setup():
    boards = FakeKanbanRepository()
    audit = FakeAuditRepository()
    users = FakeUserRepository()
    owner = await users.add(User(email="owner@amp.local", name="Owner", password_hash="x"))
    svc = KanbanService(boards=boards, audit=audit)
    return svc, boards, audit, users, owner


class TestBoards:
    async def test_create_seeds_default_columns_with_one_landing(self):
        svc, _boards, audit, _users, owner = await _setup()
        board = await svc.create_board(owner, BoardCreate(name="Sprint 1"))
        _, columns, cards = await svc.get_board_full(owner, board.id)
        assert [c.name for c in columns] == [name for name, *_ in DEFAULT_COLUMNS]
        assert sum(c.is_landing for c in columns) == 1
        assert next(c for c in columns if c.is_landing).name == "A fazer"
        # columns come back in left→right rank order
        assert [c.rank for c in columns] == sorted(c.rank for c in columns)
        assert cards == []
        assert audit.has("kanban_board_created")

    async def test_list_hides_other_users_private_board(self):
        svc, _boards, _audit, users, owner = await _setup()
        other = await users.add(User(email="o2@amp.local", name="Other", password_hash="x"))
        await svc.create_board(owner, BoardCreate(name="Privado", visibility="private"))
        team = await svc.create_board(owner, BoardCreate(name="Time", visibility="team"))
        visible = await svc.list_boards(other)
        assert [b.id for b in visible] == [team.id]

    async def test_get_private_board_of_another_user_is_404(self):
        svc, _boards, _audit, users, owner = await _setup()
        other = await users.add(User(email="o2@amp.local", name="Other", password_hash="x"))
        board = await svc.create_board(owner, BoardCreate(name="P", visibility="private"))
        with pytest.raises(NotFoundError):
            await svc.get_board(other, board.id)

    async def test_admin_sees_every_board(self):
        svc, _boards, _audit, users, owner = await _setup()
        admin = await users.add(
            User(email="a@amp.local", name="Adm", password_hash="x", role="admin")
        )
        board = await svc.create_board(owner, BoardCreate(name="P", visibility="private"))
        assert board.id in {b.id for b in await svc.list_boards(admin)}
        assert (await svc.get_board(admin, board.id)).id == board.id

    async def test_update_and_delete_are_owner_only(self):
        svc, _boards, _audit, users, owner = await _setup()
        member = await users.add(User(email="m@amp.local", name="M", password_hash="x"))
        board = await svc.create_board(owner, BoardCreate(name="Time", visibility="team"))
        # a team member can SEE it but cannot change governance
        assert (await svc.get_board(member, board.id)).id == board.id
        with pytest.raises(PermissionDeniedError):
            await svc.update_board(member, board.id, BoardUpdate(name="hack"))
        with pytest.raises(PermissionDeniedError):
            await svc.delete_board(member, board.id)
        # the owner can
        updated = await svc.update_board(owner, board.id, BoardUpdate(visibility="private"))
        assert updated.visibility == "private"
        await svc.delete_board(owner, board.id)
        with pytest.raises(NotFoundError):
            await svc.get_board(owner, board.id)


class TestColumns:
    async def test_team_member_can_manage_columns(self):
        svc, _boards, _audit, users, owner = await _setup()
        member = await users.add(User(email="m@amp.local", name="M", password_hash="x"))
        board = await svc.create_board(owner, BoardCreate(name="Time", visibility="team"))
        col = await svc.create_column(member, board.id, ColumnCreate(name="Bloqueado"))
        assert col.rank > (await svc.get_board_full(owner, board.id))[1][-2].rank
        await svc.update_column(member, board.id, col.id, ColumnUpdate(name="Travado", wip_limit=3))
        _, columns, _ = await svc.get_board_full(owner, board.id)
        renamed = next(c for c in columns if c.id == col.id)
        assert renamed.name == "Travado" and renamed.wip_limit == 3

    async def test_setting_landing_clears_the_previous_one(self):
        svc, _boards, _audit, _users, owner = await _setup()
        board = await svc.create_board(owner, BoardCreate(name="B"))
        _, columns, _ = await svc.get_board_full(owner, board.id)
        target = columns[0]
        await svc.update_column(owner, board.id, target.id, ColumnUpdate(is_landing=True))
        _, columns, _ = await svc.get_board_full(owner, board.id)
        assert sum(c.is_landing for c in columns) == 1
        assert next(c for c in columns if c.is_landing).id == target.id

    async def test_cannot_delete_landing_or_non_empty_column(self):
        svc, _boards, _audit, _users, owner = await _setup()
        board = await svc.create_board(owner, BoardCreate(name="B"))
        _, columns, _ = await svc.get_board_full(owner, board.id)
        landing = next(c for c in columns if c.is_landing)
        other = next(c for c in columns if not c.is_landing)
        with pytest.raises(ConflictError):
            await svc.delete_column(owner, board.id, landing.id)
        await svc.create_card(owner, board.id, CardCreate(title="x", column_id=other.id))
        with pytest.raises(ConflictError):
            await svc.delete_column(owner, board.id, other.id)


class TestCards:
    async def test_create_card_lands_in_landing_and_stamps_authenticated_creator(self):
        svc, _boards, _audit, _users, owner = await _setup()
        board = await svc.create_board(owner, BoardCreate(name="B"))
        card = await svc.create_card(owner, board.id, CardCreate(title="  Fazer login  "))
        _, columns, _ = await svc.get_board_full(owner, board.id)
        landing = next(c for c in columns if c.is_landing)
        assert card.column_id == landing.id
        assert card.title == "Fazer login"  # trimmed
        # created_by is the authenticated actor, NOT anything the client sent
        assert card.created_by == f"user:{owner.id}"
        assert card.version == 1

    async def test_appended_cards_keep_ascending_rank(self):
        svc, _boards, _audit, _users, owner = await _setup()
        board = await svc.create_board(owner, BoardCreate(name="B"))
        a = await svc.create_card(owner, board.id, CardCreate(title="a"))
        b = await svc.create_card(owner, board.id, CardCreate(title="b"))
        c = await svc.create_card(owner, board.id, CardCreate(title="c"))
        assert a.rank < b.rank < c.rank

    async def test_update_bumps_version_and_audits(self):
        svc, _boards, audit, _users, owner = await _setup()
        board = await svc.create_board(owner, BoardCreate(name="B"))
        card = await svc.create_card(owner, board.id, CardCreate(title="x"))
        updated = await svc.update_card(owner, card.id, CardUpdate(title="y", priority="high"))
        assert updated.title == "y" and updated.priority == "high"
        assert updated.version == 2
        assert audit.has("kanban_card_updated")

    async def test_stale_expected_version_is_409(self):
        svc, _boards, _audit, _users, owner = await _setup()
        board = await svc.create_board(owner, BoardCreate(name="B"))
        card = await svc.create_card(owner, board.id, CardCreate(title="x"))
        await svc.update_card(owner, card.id, CardUpdate(title="y"))  # version → 2
        with pytest.raises(ConflictError):
            await svc.update_card(owner, card.id, CardUpdate(title="z", expected_version=1))

    async def test_clear_assignee(self):
        svc, _boards, _audit, _users, owner = await _setup()
        board = await svc.create_board(owner, BoardCreate(name="B"))
        card = await svc.create_card(owner, board.id, CardCreate(title="x", assignee="backend-ana"))
        assert card.assignee == "backend-ana"
        cleared = await svc.update_card(owner, card.id, CardUpdate(clear_assignee=True))
        assert cleared.assignee is None

    async def test_card_of_invisible_board_is_404(self):
        svc, _boards, _audit, users, owner = await _setup()
        other = await users.add(User(email="o2@amp.local", name="Other", password_hash="x"))
        board = await svc.create_board(owner, BoardCreate(name="P", visibility="private"))
        card = await svc.create_card(owner, board.id, CardCreate(title="secreto"))
        with pytest.raises(NotFoundError):
            await svc.get_card(other, card.id)
        with pytest.raises(NotFoundError):
            await svc.update_card(other, card.id, CardUpdate(title="hack"))


class TestComments:
    async def test_comment_stamps_author_and_lists_in_order(self):
        svc, _boards, audit, _users, owner = await _setup()
        board = await svc.create_board(owner, BoardCreate(name="B"))
        card = await svc.create_card(owner, board.id, CardCreate(title="x"))
        c1 = await svc.add_comment(owner, card.id, CommentCreate(body="Preciso da spec de auth"))
        assert c1.author == f"user:{owner.id}"  # authenticated actor (anti-spoof)
        await svc.add_comment(owner, card.id, CommentCreate(body="segundo"))
        comments = await svc.list_comments(owner, card.id)
        assert [c.body for c in comments] == ["Preciso da spec de auth", "segundo"]
        assert audit.has("kanban_comment_added")

    async def test_comment_on_invisible_board_is_404(self):
        svc, _boards, _audit, users, owner = await _setup()
        other = await users.add(User(email="o2@amp.local", name="Other", password_hash="x"))
        board = await svc.create_board(owner, BoardCreate(name="P", visibility="private"))
        card = await svc.create_card(owner, board.id, CardCreate(title="x"))
        with pytest.raises(NotFoundError):
            await svc.add_comment(other, card.id, CommentCreate(body="intruso"))
