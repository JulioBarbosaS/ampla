"""Rate limiting in-memory (Ameaças 2 e 3).

SlidingWindowLimiter: por chave (IP nas rotas de auth).
TokenBucket: por conexão WebSocket.
Suficiente para deploy single-process; multi-process exigiria backend externo.
"""

import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, max_events: int, window_secs: float) -> None:
        self._max = max_events
        self._window = window_secs
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        events = self._events[key]
        while events and now - events[0] > self._window:
            events.popleft()
        if len(events) >= self._max:
            return False
        events.append(now)
        return True


class TokenBucket:
    def __init__(self, rate_per_minute: int, burst: int | None = None) -> None:
        self._rate = rate_per_minute / 60.0
        self._capacity = float(burst if burst is not None else max(rate_per_minute // 4, 5))
        self._tokens = self._capacity
        self._last = time.monotonic()

    def allow(self) -> bool:
        now = time.monotonic()
        self._tokens = min(self._capacity, self._tokens + (now - self._last) * self._rate)
        self._last = now
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False
