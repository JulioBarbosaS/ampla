# Plan — Phase 9: WS reliability (end-to-end ACK + heartbeat)

> Not started in code (reverted due to a context limit). This plan is the starting point for resuming. Order: **ACK first** (it solves the real data loss), heartbeat after. Remember: the protocol is mirrored hub↔bridge **in the same commit**, goldens regenerated.

## Problem it solves

Today the hub sets `delivered_at` when the `send_json` to the socket returns (`hub/app/api/routes/ws.py` · `_deliver`) — "I pushed it down the pipe", not "the recipient stored it". If the daemon goes down before persisting, the message stays marked as delivered and **doesn't come back in `pending`** → silent loss. A heartbeat is also missing → zombie connections stay "online".

## Part 1 — End-to-end ACK (at-least-once)

**Protocol** (`hub/app/schemas/ws.py` + `bridge/src/shared/protocol.ts`, same commit):
- A new client→hub frame: `AckFrame { type:"ack", message_id:int }`. Add it to the `ClientFrame` union and to `client_frame_adapter`.
- Mirror it in `protocol.ts` (it doesn't need to go into `serverFrameSchema`, since it's client→hub).

**Hub** (`ws.py`):
- Rename `_deliver` → `_dispatch(msg)`: sends to the recipient's socket + mirrors to observers, **but does NOT set `delivered_at`** and **does NOT send `delivered` to the sender**. Returns whether the socket accepted it (for `broadcast_result.offline`).
- In the agent loop (`_run_agent_connection`), handle the `AckFrame`: `mark_delivered([id])` → load the msg → send `delivered{message_id,to}` to the `from_agent` if online → (optional) re-mirror to observers with `delivered_at` set.
- Pending flush on hello: **remove** the automatic `mark_delivered` (lines ~133-140). The pending messages are sent; the daemon will ack each one.
- `_handle_send` and `_handle_broadcast`: use `_dispatch`; the `delivered` to the sender only goes out on the ack.

**Daemon** (`bridge/src/daemon/`):
- `ws-client.ts`: an `ackMessage(id: number)` method that sends `{type:"ack", message_id:id}`.
- `index.ts` `hub.on("message")`: after `store.append(...)`, if `message.id != null` → `hub.ackMessage(message.id)`. **Always ack** (even if the append deduplicated it), otherwise the hub resends forever. Dedup by id already exists in the store → correct at-least-once.

**Tests to UPDATE** (they encode the current optimistic behavior — they'll need to ack):
- `hub/tests/integration/test_ws.py`: `test_mensagem_roteada_em_tempo_real`, `test_historico_via_rest_apos_ws`, `test_threading_e_type_via_ws` → the recipient (the test client) must send an `ack` for `delivered` to arrive and `delivered_at` to be set. Create an `ack(ws, message_id)` helper in `tests/helpers.py`.
- `test_destinatario_offline_recebe_no_proximo_hello` → on reconnection, ack the pending messages before checking that the 2nd connection comes back empty.
- Broadcast (`TestBroadcastWs`): `broadcast_result.offline` is still based on "the socket didn't accept" (the ack is asynchronous).
- Golden `hub/tests/golden/ws_frames.json`: add `client.ack` (regenerate with `AMP_UPDATE_GOLDEN=1`).
- Bridge `protocol-mirror.test.ts`: cover `client.ack`.

**New test (the one that proves the fix):** a message delivered to the socket but **without an ack** → reconnect → it **comes back in pending** (it wasn't lost). Today this would fail (marked as delivered too early).

## Part 2 — Heartbeat (~30s)

Starlette doesn't expose native ping/pong easily in the `receive_text()` loop → use an **application-level heartbeat** (JSON frames):
- Frames: hub→client `{type:"ping"}` (a new server `PingFrame`) and client→hub `{type:"pong"}` (`PongFrame` client).
- Hub: an asyncio task concurrent with the receive loop that sends `ping` every `AMP_HEARTBEAT_SECS` (default 30); if 2 intervals pass with no `pong`, it closes the ws (and the `finally` already broadcasts offline). Watch out for concurrency: the main loop reads and updates `last_pong`; the ping task checks it.
- Daemon (`ws-client.ts`): when it receives a `ping`, it replies `pong` immediately. Optional: the daemon also detects a dead hub if it doesn't receive a ping within 2 intervals.
- Config: `AMP_HEARTBEAT_SECS` in `hub/app/core/config.py`.
- Tests: a ping is sent; with no pong → the connection drops. You can use a short interval in `make_settings`.

## Inspiration (research)

- ACK + dedup by id = **at-least-once** (Socket.IO, Microsoft Azure Web PubSub, WebSocket.org reconnection).
- Heartbeat 20–45s (WebSocket.org Heartbeat, Ably).
- Design convergence: "Agent Message Bus" (dev.to/linou518) has `/ack` and a heartbeat — same direction.

## Exit checklist
- [x] hub + bridge in the same commit (protocol mirrored) — ACK in `820c64f`, heartbeat in `219d3da`
- [x] goldens regenerated and diff reviewed — `client.ack`, `client.pong`, `server.ping`
- [x] tests green in all 3 parts; coverage gates intact — hub 95.8% (≥90), bridge 84.9% (≥75), web 64% (≥25)
- [x] ARCHITECTURE.md · WS protocol updated (ack/ping/pong frames; new `delivered_at` semantics)

## Completed on 2026-06-07

Part 1 (ACK) and Part 2 (heartbeat) implemented and green. Decisions beyond the plan:
- **Web also updated** (in the ACK commit): the observer handles `delivered` and the store stamps the bubble — without this the dashboard would stay stuck on "pending" (the dispatch mirrors with `delivered_at` null, and dedup by id would ignore a re-mirror).
- **Heartbeat on agent connections only** (not observers): the goal is correcting presence, and observers don't appear in presence. `AMP_HEARTBEAT_SECS` is a `float` to allow a short interval in tests.
- **Ownership on the ack**: only the recipient itself marks its own message as delivered (Threat 3).
- The daemon detecting a dead hub via ping-timeout (the "optional" item in Part 2): **not done** — the TCP `close` already triggers the reconnect; half-open detection on the daemon side is left for later if needed.
