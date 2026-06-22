"""Card dependencies / DAG (Epic 06 · 6.7): blocking edges, cycle rejection, and
the gate that stops a blocked card from reaching a done column."""

import pytest

from app.models.user import User
from app.schemas.kanban import BoardCreate, CardCreate
from app.services.errors import ConflictError, InvalidInputError
from app.services.kanban_service import KanbanService
from tests.unit.fakes import FakeAuditRepository, FakeKanbanRepository, FakeUserRepository


async def _setup():
    boards = FakeKanbanRepository()
    users = FakeUserRepository()
    owner = await users.add(User(email="o@amp.local", name="O", password_hash="x"))
    svc = KanbanService(boards=boards, audit=FakeAuditRepository())
    board = await svc.create_board(owner, BoardCreate(name="B"))
    a = await svc.create_card(owner, board.id, CardCreate(title="A"))
    b = await svc.create_card(owner, board.id, CardCreate(title="B"))
    return svc, owner, board, a, b


async def _columns(svc, owner, board_id):
    _, columns, _ = await svc.get_board_full(owner, board_id)
    return columns


class TestDependencies:
    async def test_add_and_list_dependency(self):
        svc, owner, _board, a, b = await _setup()
        await svc.add_dependency(owner, a.id, b.id)  # A blocked by B
        deps = await svc.list_dependencies(owner, a.id)
        assert [d.id for d in deps] == [b.id]

    async def test_self_dependency_rejected(self):
        svc, owner, _board, a, _b = await _setup()
        with pytest.raises(InvalidInputError):
            await svc.add_dependency(owner, a.id, a.id)

    async def test_cycle_is_rejected(self):
        svc, owner, _board, a, b = await _setup()
        await svc.add_dependency(owner, a.id, b.id)  # A → B
        with pytest.raises(ConflictError):
            await svc.add_dependency(owner, b.id, a.id)  # B → A would close a cycle

    async def test_board_full_exposes_depends_on(self):
        svc, owner, board, a, b = await _setup()
        await svc.add_dependency(owner, a.id, b.id)
        _, _, cards = await svc.get_board_full(owner, board.id)
        by_id = {c.id: c for c in cards}
        assert by_id[a.id].depends_on == [b.id]
        assert by_id[b.id].depends_on == []

    async def test_blocked_card_cannot_enter_a_done_column(self):
        svc, owner, board, a, b = await _setup()
        await svc.add_dependency(owner, a.id, b.id)  # A blocked by B (B not done)
        done = next(c for c in await _columns(svc, owner, board.id) if c.is_done)
        with pytest.raises(ConflictError):
            await svc.move_card(
                owner, a.id, done.id, before_id=None, after_id=None, expected_version=a.version
            )

    async def test_card_enters_done_once_dependency_is_done(self):
        svc, owner, board, a, b = await _setup()
        cols = await _columns(svc, owner, board.id)
        done = next(c for c in cols if c.is_done)
        await svc.add_dependency(owner, a.id, b.id)
        # finish B first → A is unblocked
        b2 = await svc.move_card(
            owner, b.id, done.id, before_id=None, after_id=None, expected_version=b.version
        )
        assert b2.column_id == done.id
        a2 = await svc.move_card(
            owner, a.id, done.id, before_id=None, after_id=None, expected_version=a.version
        )
        assert a2.column_id == done.id

    async def test_remove_dependency(self):
        svc, owner, _board, a, b = await _setup()
        await svc.add_dependency(owner, a.id, b.id)
        await svc.remove_dependency(owner, a.id, b.id)
        assert await svc.list_dependencies(owner, a.id) == []
