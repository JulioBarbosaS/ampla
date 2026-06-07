"""Rate limiting in-memory (Ameaças 2 e 3).

SlidingWindowLimiter: por chave (IP nas rotas de auth).
TokenBucket: por conexão WebSocket.
Suficiente para deploy single-process; multi-process exigiria backend externo.

`clock` é injetável (default time.monotonic) — permite property tests
determinísticos sobre as invariantes de limite.
"""

import time
from collections import defaultdict, deque
from collections.abc import Callable

Clock = Callable[[], float]


class SlidingWindowLimiter:
    def __init__(self, max_events: int, window_secs: float, clock: Clock = time.monotonic) -> None:
        self._max = max_events
        self._window = window_secs
        self._clock = clock
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = self._clock()
        events = self._events[key]
        while events and now - events[0] > self._window:
            events.popleft()
        if len(events) >= self._max:
            return False
        events.append(now)
        return True


class TokenBucket:
    def __init__(
        self, rate_per_minute: int, burst: int | None = None, clock: Clock = time.monotonic
    ) -> None:
        self._rate = rate_per_minute / 60.0
        self._capacity = float(burst if burst is not None else max(rate_per_minute // 4, 5))
        self._tokens = self._capacity
        self._clock = clock
        self._last = clock()

    def allow(self) -> bool:
        now = self._clock()
        self._tokens = min(self._capacity, self._tokens + (now - self._last) * self._rate)
        self._last = now
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False
