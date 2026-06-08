"""Registry of active connections: agent daemons and observers (panel).

Transport layer — the only part of the hub (besides the WS routes) that touches
the raw WebSocket. Services interact only with this abstraction.
"""

import asyncio
from dataclasses import dataclass, field

from fastapi import WebSocket


@dataclass
class ObserverConn:
    ws: WebSocket
    user_id: int
    role: str
    owned_slugs: set[str] = field(default_factory=set)

    def can_see(self, from_slug: str, to_slug: str) -> bool:
        return self.role == "admin" or bool(self.owned_slugs & {from_slug, to_slug})


class ConnectionManager:
    def __init__(self) -> None:
        self._agents: dict[str, WebSocket] = {}
        self._observers: list[ObserverConn] = []
        self._lock = asyncio.Lock()

    # ---- agents (daemons) ----

    async def connect_agent(self, slug: str, ws: WebSocket) -> None:
        async with self._lock:
            old = self._agents.get(slug)
            self._agents[slug] = ws
        if old is not None:
            # The new connection replaces the old one (reconnect or stolen key —
            # in both cases the old one must not keep receiving)
            await self._close_quietly(old, code=4000, reason="replaced")

    async def disconnect_agent(self, slug: str, ws: WebSocket) -> bool:
        """Removes it if it is still the current connection. True if removed."""
        async with self._lock:
            if self._agents.get(slug) is ws:
                del self._agents[slug]
                return True
        return False

    async def kick_agent(self, slug: str, reason: str = "revoked") -> bool:
        """Drops the daemon immediately (key revocation — Threat 2).
        Returns True if there was a connection. Broadcasting the `offline` presence
        is the caller's responsibility (the dropped connection's loop does not emit
        it, since disconnect_agent no longer finds the slug)."""
        async with self._lock:
            ws = self._agents.pop(slug, None)
        if ws is not None:
            await self._close_quietly(ws, code=4001, reason=reason)
            return True
        return False

    def is_online(self, slug: str) -> bool:
        return slug in self._agents

    def online_slugs(self) -> list[str]:
        return sorted(self._agents)

    async def send_to_agent(self, slug: str, payload: dict) -> bool:
        ws = self._agents.get(slug)
        if ws is None:
            return False
        try:
            await ws.send_json(payload)
            return True
        except Exception:
            return False

    # ---- observers (human panel) ----

    async def add_observer(self, conn: ObserverConn) -> None:
        async with self._lock:
            self._observers.append(conn)

    async def remove_observer(self, ws: WebSocket) -> None:
        async with self._lock:
            self._observers = [o for o in self._observers if o.ws is not ws]

    # ---- broadcasts ----

    async def broadcast_presence(self, payload: dict) -> None:
        for ws in list(self._agents.values()):
            await self._send_quietly(ws, payload)
        for obs in list(self._observers):
            await self._send_quietly(obs.ws, payload)

    async def notify_message(self, payload: dict, from_slug: str, to_slug: str) -> None:
        """Mirrors the message to authorized observers (owner or admin)."""
        for obs in list(self._observers):
            if obs.can_see(from_slug, to_slug):
                await self._send_quietly(obs.ws, payload)

    async def send_settings_update(self, slug: str, payload: dict) -> bool:
        return await self.send_to_agent(slug, payload)

    # ---- internals ----

    @staticmethod
    async def _send_quietly(ws: WebSocket, payload: dict) -> None:
        try:
            await ws.send_json(payload)
        except Exception:  # noqa: S110 — best-effort broadcast
            pass  # a dead connection is removed by its own loop

    @staticmethod
    async def _close_quietly(ws: WebSocket, code: int, reason: str) -> None:
        try:
            await ws.close(code=code, reason=reason)
        except Exception:  # noqa: S110 — closing an already-dead connection is a no-op
            pass
