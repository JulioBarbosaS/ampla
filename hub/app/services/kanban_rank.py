"""Fractional rank strings for Kanban ordering (Epic 06 · 6.2 core).

A card's (or column's) position is a short, lexicographically-sorted string
(LexoRank / fractional-indexing style). Inserting or moving an item computes a
``rank_between`` the two neighbours at the destination, so only the moved item's
rank changes — an O(1) move with no row-shifting. The string can grow on
repeated splits in the same gap; ``rebalance_ranks`` re-spreads a column evenly
when that happens (Epic 06 · 6.2).

Pure module (no I/O) so the ordering algebra can be exhaustively property-tested.

The alphabet is in ascending ASCII order ('0'..'9' < 'A'..'Z' < 'a'..'z'), so a
plain string comparison matches a digit-by-digit comparison of the ranks — what
lets the DB sort by the `rank` column directly.
"""

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
BASE = len(ALPHABET)  # 62
_INDEX = {ch: i for i, ch in enumerate(ALPHABET)}

# A fresh, balanced first rank for an empty column (the alphabet's midpoint).
FIRST_RANK = ALPHABET[BASE // 2]


def rank_between(lo: str | None, hi: str | None) -> str:
    """A rank strictly between ``lo`` and ``hi`` (which must satisfy lo < hi).

    ``lo=None``/``""`` means "before the first item"; ``hi=None``/``""`` means
    "after the last item". Both empty → the first rank on an empty column. The
    result never ends in the lowest digit, so a later split below it always has
    room.
    """
    lo = lo or ""
    upper_unbounded = not hi  # "" or None both mean +infinity
    prefix: list[str] = []
    n = 0
    while True:
        lo_code = _INDEX[lo[n]] if n < len(lo) else 0
        if upper_unbounded:
            hi_code = BASE
        else:
            # Under the lo < hi contract, hi can never be exhausted before lo
            # diverges, so an in-range index always exists here.
            hi_code = _INDEX[hi[n]] if n < len(hi) else 0  # type: ignore[index]
        if lo_code == hi_code:
            prefix.append(ALPHABET[lo_code])
            n += 1
            continue
        mid = (lo_code + hi_code) // 2
        if mid != lo_code:
            prefix.append(ALPHABET[mid])
            return "".join(prefix)
        # lo and hi are adjacent at this digit (hi = lo + 1): nothing fits
        # between them here, so keep lo's digit and descend with no upper bound.
        prefix.append(ALPHABET[lo_code])
        upper_unbounded = True
        n += 1


def rebalance_ranks(count: int) -> list[str]:
    """``count`` evenly-spaced ranks in ascending order, for re-spreading a column.

    Single pass over ``rank_between`` from the previous anchor; short and stable
    for the hundreds-of-cards scale a local board reaches.
    """
    if count <= 0:
        return []
    ranks: list[str] = []
    prev: str | None = None
    for _ in range(count):
        nxt = rank_between(prev, None)
        ranks.append(nxt)
        prev = nxt
    return ranks


def max_rank_len(ranks: list[str]) -> int:
    """Longest rank string in a column — the rebalance trigger (Epic 06 · 6.2)."""
    return max((len(r) for r in ranks), default=0)
