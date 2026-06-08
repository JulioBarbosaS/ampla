"""Property-based tests (hypothesis) — invariants that hold for ANY
input, not just the examples we remember to write.

Focused on the adversarial pressure points: rate limiters, slug validation
and the WS protocol round-trip.
"""

import re

from hypothesis import given
from hypothesis import strategies as st

from app.core.ratelimit import SlidingWindowLimiter, TokenBucket
from app.schemas.agent import SLUG_PATTERN
from app.schemas.ws import SendMessageFrame, client_frame_adapter

_SLUG_RE = re.compile(SLUG_PATTERN)

# ---------------------------------------------------------------- limiters


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, secs: float) -> None:
        self.now += secs


@given(
    deltas=st.lists(st.floats(min_value=0.0, max_value=5.0), min_size=1, max_size=200),
    max_events=st.integers(min_value=1, max_value=20),
    window=st.floats(min_value=1.0, max_value=60.0),
)
def test_sliding_window_never_exceeds_the_max_in_any_window(deltas, max_events, window):
    """Invariant: for any sequence of arrivals, the number of ALLOWED events
    within any window never exceeds max_events."""
    clock = FakeClock()
    limiter = SlidingWindowLimiter(max_events, window, clock=clock)
    allowed_times: list[float] = []

    for delta in deltas:
        clock.advance(delta)
        if limiter.allow("ip"):
            allowed_times.append(clock.now)

    for i, start in enumerate(allowed_times):
        in_window = [t for t in allowed_times[i:] if t - start <= window]
        assert len(in_window) <= max_events


@given(
    deltas=st.lists(st.floats(min_value=0.0, max_value=10.0), min_size=1, max_size=300),
    rate=st.integers(min_value=1, max_value=120),
)
def test_token_bucket_respects_burst_plus_rate(deltas, rate):
    """Invariant: allowed ≤ initial capacity + rate × elapsed time."""
    clock = FakeClock()
    bucket = TokenBucket(rate, clock=clock)
    capacity = max(rate // 4, 5)

    allowed = 0
    elapsed = 0.0
    for delta in deltas:
        clock.advance(delta)
        elapsed += delta
        if bucket.allow():
            allowed += 1

    assert allowed <= capacity + (rate / 60.0) * elapsed + 1e-6


# ---------------------------------------------------------------- slug


@given(slug=st.from_regex(SLUG_PATTERN, fullmatch=True))
def test_valid_slug_has_the_guaranteed_properties(slug):
    assert slug == slug.lower()
    assert 3 <= len(slug) <= 50
    assert not slug.startswith("-") and not slug.endswith("-")


@given(text=st.text(min_size=1, max_size=60))
def test_accepted_slug_implies_safe_characters(text):
    """Any string accepted by the pattern contains only [a-z0-9-] — never
    spaces, uppercase, unicode or metacharacters."""
    if _SLUG_RE.fullmatch(text):
        assert re.fullmatch(r"[a-z0-9-]+", text)


# ---------------------------------------------------------------- protocol


@given(
    to=st.from_regex(SLUG_PATTERN, fullmatch=True),
    body=st.text(min_size=1, max_size=2000),
    msg_type=st.sampled_from(
        ["request", "response", "notification", "task", "alert", "status", "ack"]
    ),
    priority=st.sampled_from(["urgent", "high", "normal", "low"]),
    in_reply_to=st.one_of(st.none(), st.integers(min_value=1, max_value=10**9)),
)
def test_send_frame_roundtrip_serializes_and_returns_identical(
    to, body, msg_type, priority, in_reply_to
):
    """Round-trip: any valid frame survives serialize→parse,
    including bodies with unicode, quotes, control chars and emoji."""
    frame = SendMessageFrame(
        to=to, body=body, msg_type=msg_type, priority=priority, in_reply_to=in_reply_to
    )
    parsed = client_frame_adapter.validate_json(frame.model_dump_json())
    assert parsed == frame
