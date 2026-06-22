"""Fractional-rank algebra (Epic 06 · 6.2 core) — deterministic basics.
Exhaustive property/concurrency coverage is added in the 6.2 slice."""

from app.services.kanban_rank import FIRST_RANK, rank_between, rebalance_ranks


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
