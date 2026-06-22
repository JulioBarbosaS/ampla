"""Fractional-rank algebra (Epic 06 · 6.2 core): deterministic cases + the
hypothesis property that ANY sequence of inserts/moves keeps the order sorted
and ranks unique (the invariant the whole board ordering rests on)."""

from hypothesis import given
from hypothesis import strategies as st

from app.services.kanban_rank import (
    FIRST_RANK,
    RANK_LEN_MAX,
    max_rank_len,
    rank_between,
    rebalance_ranks,
)


class TestRankBetween:
    def test_first_rank_on_empty_column(self):
        assert rank_between(None, None) == FIRST_RANK

    def test_append_after_is_strictly_greater(self):
        a = rank_between(None, None)
        b = rank_between(a, None)
        assert a < b

    def test_prepend_before_is_strictly_smaller(self):
        a = rank_between(None, None)
        b = rank_between(None, a)
        assert b < a

    def test_midpoint_is_strictly_between_neighbours(self):
        lo = rank_between(None, None)
        hi = rank_between(lo, None)
        mid = rank_between(lo, hi)
        assert lo < mid < hi

    def test_repeated_splits_in_the_same_gap_stay_ordered(self):
        lo = rank_between(None, None)
        hi = rank_between(lo, None)
        prev = hi
        for _ in range(50):
            mid = rank_between(lo, prev)
            assert lo < mid < prev
            prev = mid

    def test_never_ends_in_the_lowest_digit(self):
        # so a later split below it always has room
        ranks = [rank_between(None, None)]
        for _ in range(20):
            ranks.append(rank_between(ranks[-1], None))
        assert all(not r.endswith("0") for r in ranks)


class TestRebalance:
    def test_rebalance_returns_ascending_unique_ranks(self):
        ranks = rebalance_ranks(100)
        assert len(ranks) == 100
        assert ranks == sorted(ranks)
        assert len(set(ranks)) == 100

    def test_rebalance_empty(self):
        assert rebalance_ranks(0) == []


class TestOrderingInvariants:
    """Property: for any sequence of insert/move operations, the resulting ranks
    stay strictly sorted in their intended logical order and never duplicate."""

    @given(positions=st.lists(st.integers(min_value=0, max_value=10**6), min_size=1, max_size=80))
    def test_arbitrary_inserts_stay_sorted_and_unique(self, positions):
        ranks: list[str] = []
        for p in positions:
            i = p % (len(ranks) + 1)  # an in-range insertion slot
            lo = ranks[i - 1] if i > 0 else None
            hi = ranks[i] if i < len(ranks) else None
            r = rank_between(lo, hi)
            # strictly between its neighbours
            assert lo is None or lo < r
            assert hi is None or r < hi
            ranks.insert(i, r)
        assert ranks == sorted(ranks)
        assert len(set(ranks)) == len(ranks)

    @given(
        moves=st.lists(
            st.tuples(
                st.integers(min_value=0, max_value=999), st.integers(min_value=0, max_value=999)
            ),
            min_size=1,
            max_size=60,
        )
    )
    def test_moves_preserve_sorted_unique_invariant(self, moves):
        # seed a small column, then repeatedly pluck a card and reinsert it
        ranks = rebalance_ranks(5)
        for src, dst in moves:
            if not ranks:
                break
            r = ranks.pop(src % len(ranks))  # noqa: F841 — removed, recomputed below
            i = dst % (len(ranks) + 1)
            lo = ranks[i - 1] if i > 0 else None
            hi = ranks[i] if i < len(ranks) else None
            ranks.insert(i, rank_between(lo, hi))
        assert ranks == sorted(ranks)
        assert len(set(ranks)) == len(ranks)

    def test_adversarial_same_gap_inserts_trigger_growth_then_rebalance_resets(self):
        # always splitting the SAME low gap is the worst case → ranks lengthen
        lo = rank_between(None, None)
        hi = rank_between(lo, None)
        col = [lo, hi]
        for _ in range(80):
            col.insert(1, rank_between(col[0], col[1]))
        assert col == sorted(col) and len(set(col)) == len(col)
        # a rebalance collapses the length back to the minimum
        rebalanced = rebalance_ranks(len(col))
        assert max_rank_len(rebalanced) <= RANK_LEN_MAX
        assert rebalanced == sorted(rebalanced)
