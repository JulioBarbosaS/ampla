"""Card move + concurrency core (Epic 06 · 6.2) at the service layer, against
the fake repo (which enforces the same unique-(column,rank) backstop + WIP-in-
write the real repo does). Covers: anchor-based reorder, optimistic version,
the collision squeeze, WIP TOCTOU, and the move-triggered rebalance."""

import pytest

from app.models.user import User
from app.schemas.kanban import BoardCreate, CardCreate, ColumnUpdate
from app.services.errors import ConflictError, InvalidInputError
from app.services.kanban_rank import RANK_LEN_MAX
from app.services.kanban_service import KanbanService
from tests.unit.fakes import FakeAuditRepository, FakeKanbanRepository, FakeUserRepository


async def _setup():
    boards = FakeKanbanRepository()
    users = FakeUserRepository()
    owner = await users.add(User(email="owner@amp.local", name="Owner", password_hash="x"))
    svc = KanbanService(boards=boards, audit=FakeAuditRepository())
    return svc, boards, owner


async def _board_with_cards(svc, owner, n):
    board = await svc.create_board(owner, BoardCreate(name="B"))
    _, columns, _ = await svc.get_board_full(owner, board.id)
    landing = next(c for c in columns if c.is_landing)
    other = next(c for c in columns if not c.is_landing)
    cards = [
        await svc.create_card(owner, board.id, CardCreate(title=f"c{i}", column_id=landing.id))
        for i in range(n)
    ]
    return board, landing, other, cards


async def _column_order(svc, owner, board_id, column_id):
    _, _, cards = await svc.get_board_full(owner, board_id)
    incol = sorted((c for c in cards if c.column_id == column_id), key=lambda c: c.rank)
    return incol


class TestMove:
    async def test_anchor_move_reorders_within_column(self):
        svc, _boards, owner = await _setup()
        board, landing, _other, (a, b, c) = await _board_with_cards(svc, owner, 3)
        assert a.rank < b.rank < c.rank
        moved = await svc.move_card(
            owner, c.id, landing.id, before_id=a.id, after_id=b.id, expected_version=c.version
        )
        assert a.rank < moved.rank < b.rank
        order = await _column_order(svc, owner, board.id, landing.id)
        assert [x.id for x in order] == [a.id, c.id, b.id]

    async def test_move_to_another_column_updates_column_id(self):
        svc, _boards, owner = await _setup()
        board, landing, other, (a,) = await _board_with_cards(svc, owner, 1)
        moved = await svc.move_card(
            owner, a.id, other.id, before_id=None, after_id=None, expected_version=a.version
        )
        assert moved.column_id == other.id

    async def test_stale_version_is_409(self):
        svc, _boards, owner = await _setup()
        board, landing, _other, (a, b, c) = await _board_with_cards(svc, owner, 3)
        with pytest.raises(ConflictError):
            await svc.move_card(
                owner, c.id, landing.id, before_id=a.id, after_id=b.id, expected_version=999
            )

    async def test_self_anchor_is_rejected(self):
        svc, _boards, owner = await _setup()
        board, landing, _other, (a,) = await _board_with_cards(svc, owner, 1)
        with pytest.raises(InvalidInputError):
            await svc.move_card(
                owner, a.id, landing.id, before_id=a.id, after_id=None, expected_version=a.version
            )

    async def test_stale_anchor_no_longer_in_column_is_409(self):
        svc, _boards, owner = await _setup()
        board, landing, other, (a, b) = await _board_with_cards(svc, owner, 2)
        # b moved away; a client still anchoring on b in `landing` is stale
        await svc.move_card(
            owner, b.id, other.id, before_id=None, after_id=None, expected_version=b.version
        )
        with pytest.raises(ConflictError):
            await svc.move_card(
                owner, a.id, landing.id, before_id=b.id, after_id=None, expected_version=a.version
            )


class TestConcurrency:
    async def test_two_moves_into_the_same_gap_stay_ordered_and_unique(self):
        """The unique-rank backstop: the second move collides on the midpoint,
        squeezes below it, and both cards land between the anchors — no duplicate
        rank, no lost card."""
        svc, _boards, owner = await _setup()
        board, landing, _other, (a, b, c, d) = await _board_with_cards(svc, owner, 4)
        await svc.move_card(
            owner, c.id, landing.id, before_id=a.id, after_id=b.id, expected_version=c.version
        )
        await svc.move_card(
            owner, d.id, landing.id, before_id=a.id, after_id=b.id, expected_version=d.version
        )
        order = await _column_order(svc, owner, board.id, landing.id)
        ranks = [x.rank for x in order]
        assert ranks == sorted(ranks)
        assert len(set(ranks)) == len(ranks)  # collision resolved, no duplicate
        pos = {x.id: i for i, x in enumerate(order)}
        assert pos[a.id] < pos[c.id] < pos[b.id]
        assert pos[a.id] < pos[d.id] < pos[b.id]


class TestWipLimit:
    async def test_move_into_a_full_column_is_rejected(self):
        svc, _boards, owner = await _setup()
        board = await svc.create_board(owner, BoardCreate(name="B"))
        _, cols, _ = await svc.get_board_full(owner, board.id)
        landing = next(c for c in cols if c.is_landing)
        other = next(c for c in cols if not c.is_landing)
        await svc.update_column(owner, board.id, landing.id, ColumnUpdate(wip_limit=1))
        await svc.create_card(owner, board.id, CardCreate(title="1", column_id=landing.id))
        intruder = await svc.create_card(owner, board.id, CardCreate(title="2", column_id=other.id))
        with pytest.raises(ConflictError):
            await svc.move_card(
                owner,
                intruder.id,
                landing.id,
                before_id=None,
                after_id=None,
                expected_version=intruder.version,
            )

    async def test_sequential_moves_into_a_capped_column_land_only_the_limit(self):
        svc, _boards, owner = await _setup()
        board = await svc.create_board(owner, BoardCreate(name="B"))
        _, cols, _ = await svc.get_board_full(owner, board.id)
        landing = next(c for c in cols if c.is_landing)
        other = next(c for c in cols if not c.is_landing)
        await svc.update_column(owner, board.id, landing.id, ColumnUpdate(wip_limit=2))
        cards = [
            await svc.create_card(owner, board.id, CardCreate(title=str(i), column_id=other.id))
            for i in range(3)
        ]
        landed = 0
        for c in cards:
            try:
                await svc.move_card(
                    owner,
                    c.id,
                    landing.id,
                    before_id=None,
                    after_id=None,
                    expected_version=c.version,
                )
                landed += 1
            except ConflictError:
                pass
        assert landed == 2
        order = await _column_order(svc, owner, board.id, landing.id)
        assert len(order) == 2


class TestRebalance:
    async def test_move_into_an_exhausted_gap_rebalances_then_places(self):
        svc, _boards, owner = await _setup()
        board, landing, _other, (a, b) = await _board_with_cards(svc, owner, 2)
        # Force a near-maximal, adjacent-at-depth gap so the midpoint overflows
        # RANK_LEN_MAX and the move must rebalance the column first.
        a.rank = "a" * RANK_LEN_MAX
        b.rank = "a" * (RANK_LEN_MAX - 1) + "b"
        c = await svc.create_card(owner, board.id, CardCreate(title="c", column_id=landing.id))
        moved = await svc.move_card(
            owner, c.id, landing.id, before_id=a.id, after_id=b.id, expected_version=c.version
        )
        order = await _column_order(svc, owner, board.id, landing.id)
        assert all(len(x.rank) <= RANK_LEN_MAX for x in order)  # rebalance collapsed lengths
        pos = {x.id: i for i, x in enumerate(order)}
        assert pos[a.id] < pos[moved.id] < pos[b.id]
