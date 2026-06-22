"""KanbanRepository concurrency primitives against REAL SQLite (Epic 06 · 6.2):
the unique-(column_id, rank) backstop that `commit_move` relies on, and the
two-pass `rebalance_column` that must re-spread ranks WITHOUT tripping that same
index mid-update."""

import pytest_asyncio

from app.core.db import build_engine, build_session_factory, create_tables
from app.models.kanban import KanbanBoard, KanbanCard, KanbanColumn
from app.models.user import User
from app.repositories.kanban_repo import KanbanRepository
from app.repositories.user_repo import UserRepository


@pytest_asyncio.fixture
async def session():
    engine = build_engine("sqlite+aiosqlite:///:memory:")
    await create_tables(engine)
    factory = build_session_factory(engine)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _board_with_column(session) -> tuple[int, int]:
    owner = await UserRepository(session).add(
        User(email="o@amp.local", name="O", password_hash="x", role="admin")
    )
    repo = KanbanRepository(session)
    board = await repo.add_board(KanbanBoard(owner_id=owner.id, name="B"))
    col = await repo.add_column(KanbanColumn(board_id=board.id, name="todo", rank="m"))
    return board.id, col.id


class TestCommitMove:
    async def test_unique_rank_collision_returns_collision(self, session):
        board_id, col_id = await _board_with_column(session)
        repo = KanbanRepository(session)
        a = await repo.add_card(
            KanbanCard(
                board_id=board_id, column_id=col_id, rank="a", title="a", created_by="user:1"
            )
        )
        b = await repo.add_card(
            KanbanCard(
                board_id=board_id, column_id=col_id, rank="b", title="b", created_by="user:1"
            )
        )
        # try to move b onto a's exact rank → the unique index trips → "collision"
        result = await repo.commit_move(b, col_id, "a", None)
        assert result == "collision"
        # the rollback left both cards intact at their original ranks (fresh SELECT)
        by_rank = {c.id: c.rank for c in await repo.list_cards_in_column(col_id)}
        versions = {c.id: c.version for c in await repo.list_cards_in_column(col_id)}
        assert by_rank == {a.id: "a", b.id: "b"}
        assert versions[b.id] == 1

    async def test_move_into_full_column_returns_wip_full(self, session):
        board_id, col_id = await _board_with_column(session)
        repo = KanbanRepository(session)
        dest = await repo.add_column(
            KanbanColumn(board_id=board_id, name="doing", rank="t", wip_limit=1)
        )
        await repo.add_card(
            KanbanCard(
                board_id=board_id, column_id=dest.id, rank="a", title="x", created_by="user:1"
            )
        )
        mover = await repo.add_card(
            KanbanCard(
                board_id=board_id, column_id=col_id, rank="a", title="y", created_by="user:1"
            )
        )
        assert await repo.commit_move(mover, dest.id, "k", 1) == "wip_full"

    async def test_successful_move_bumps_version_and_column(self, session):
        board_id, col_id = await _board_with_column(session)
        repo = KanbanRepository(session)
        dest = await repo.add_column(KanbanColumn(board_id=board_id, name="doing", rank="t"))
        card = await repo.add_card(
            KanbanCard(
                board_id=board_id, column_id=col_id, rank="a", title="x", created_by="user:1"
            )
        )
        assert await repo.commit_move(card, dest.id, "k", None) == "ok"
        fresh = await repo.get_card(card.id)
        assert fresh.column_id == dest.id and fresh.rank == "k" and fresh.version == 2


class TestRebalance:
    async def test_rebalance_reassigns_overlapping_ranks_without_unique_violation(self, session):
        board_id, col_id = await _board_with_column(session)
        repo = KanbanRepository(session)
        for r in ("a", "b", "c"):
            await repo.add_card(
                KanbanCard(
                    board_id=board_id, column_id=col_id, rank=r, title=r, created_by="user:1"
                )
            )
        # New ranks OVERLAP the old set ({b,c} are shared): a naive one-pass update
        # would violate the unique index. The two-pass temp namespace must avoid it.
        rebalanced = await repo.rebalance_column(col_id, ["b", "c", "d"])
        assert [c.rank for c in sorted(rebalanced, key=lambda c: c.rank)] == ["b", "c", "d"]
        # persisted + versions bumped
        cards = await repo.list_cards_in_column(col_id)
        assert [c.rank for c in cards] == ["b", "c", "d"]
        assert all(c.version == 2 for c in cards)
