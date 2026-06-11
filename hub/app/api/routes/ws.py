"""WebSocket endpoint: agent daemons and panel observers.

Transport layer: parses/serializes frames and orchestrates
services + ConnectionManager. Never touches repositories directly —
services are built via local factories with one session per operation.

Security (docs/ARCHITECTURE.md · Threat 3): hello required within 10s,
frame size limit, per-connection token bucket, disconnect after repeated
malformed frames.
"""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.api.deps import (
    build_agent_service,
    build_auth_service,
    build_autorespond_service,
    build_group_service,
    build_message_service,
)
from app.core.cookies import SESSION_COOKIE
from app.core.ratelimit import TokenBucket
from app.schemas.agent import AgentSettings
from app.schemas.message import MessageOut
from app.schemas.ws import (
    AckFrame,
    ActivityFrame,
    AgentActivityFrame,
    AutorespondReportFrame,
    BroadcastResultFrame,
    DeliveredFrame,
    ErrorFrame,
    GroupInfo,
    HelloAckFrame,
    HelloFrame,
    MessageDeliveryFrame,
    PingFrame,
    PongFrame,
    SendMessageFrame,
    client_frame_adapter,
)
from app.services.errors import DomainError
from app.services.message_service import MessageService
from app.ws.connection_manager import ConnectionManager, ObserverConn

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_MALFORMED_FRAMES = 5

# Custom close codes (4xxx = application)
CLOSE_BAD_HELLO = 4400
CLOSE_AUTH_FAIL = 4401
CLOSE_PROTOCOL_ABUSE = 4429
CLOSE_HEARTBEAT_TIMEOUT = 4408  # zombie: 2 cycles without a frame — daemon reconnects


def _message_payload(msg) -> dict:
    return MessageDeliveryFrame(message=MessageOut.model_validate(msg)).model_dump(
        mode="json", by_alias=True
    )


async def _send_error(ws: WebSocket, code: str, detail: str) -> None:
    await ws.send_json(ErrorFrame(code=code, detail=detail).model_dump(mode="json"))


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    state = ws.app.state
    settings = state.settings

    # ---- hello required within the timeout ----
    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=settings.ws_hello_timeout_secs)
    except WebSocketDisconnect:
        return  # client gave up before the hello
    except TimeoutError:
        await ws.close(code=CLOSE_BAD_HELLO, reason="hello timeout")
        return

    if len(raw.encode()) > settings.ws_max_frame_bytes:
        await ws.close(code=CLOSE_PROTOCOL_ABUSE, reason="frame too large")
        return

    try:
        hello = HelloFrame.model_validate_json(raw)
    except ValidationError:
        await ws.close(code=CLOSE_BAD_HELLO, reason="expected hello frame")
        return

    if hello.agent_id and hello.key:
        await _run_agent_connection(ws, hello)
    elif hello.jwt or ws.cookies.get(SESSION_COOKIE):
        # Panel observer: the browser carries the session cookie on the WS
        # upgrade (same origin); programmatic observers may still pass jwt.
        await _run_observer_connection(ws, hello)
    else:
        await _send_error(ws, "bad_hello", "Informe (agent_id, key) ou jwt.")
        await ws.close(code=CLOSE_BAD_HELLO, reason="incomplete hello")


# ---------------------------------------------------------------- daemons


async def _run_agent_connection(ws: WebSocket, hello: HelloFrame) -> None:
    state = ws.app.state
    settings = state.settings
    manager: ConnectionManager = state.manager
    session_factory = state.session_factory
    slug = hello.agent_id

    # authentication + initial snapshot (short-lived session)
    async with session_factory() as session:
        agent = await build_agent_service(session).authenticate_key(slug, hello.key or "")
        if agent is None:
            await _send_error(ws, "auth_failed", "Chave inválida ou revogada.")
            await ws.close(code=CLOSE_AUTH_FAIL, reason="auth failed")
            return
        pending = await _message_service(ws, session).pending_for(slug)
        agent_settings = AgentSettings.model_validate(agent)
        groups = [
            GroupInfo(slug=g.slug, display_name=g.display_name, members=members)
            for g, members in await build_group_service(session).list_with_members()
        ]

    await manager.connect_agent(slug, ws)
    await manager.broadcast_presence({"type": "presence", "agent_id": slug, "status": "online"})

    ack = HelloAckFrame(
        agent_id=slug,
        online=manager.online_slugs(),
        settings=agent_settings,
        pending=[MessageOut.model_validate(m) for m in pending],
        groups=groups,
        auto_responder_enabled=getattr(state, "auto_responder_enabled", True),
    )
    await ws.send_json(ack.model_dump(mode="json", by_alias=True))

    # Pending messages ride along in the hello_ack; the daemon will ack each one
    # (at-least-once). Without the ack they stay pending and come back on the next
    # reconnect — no optimistic delivered-marking here (docs/ARCHITECTURE.md · WS protocol).

    bucket = TokenBucket(settings.ws_messages_per_minute)
    malformed = 0

    # Heartbeat (Threat 3 · zombie connection): pings every interval; if 2 cycles
    # pass without ANY frame (pong included), the connection is dead — close it,
    # and the finally block broadcasts offline. asyncio is single-threaded, so
    # last_seen is read by the task and written by the loop without a race.
    loop = asyncio.get_running_loop()
    interval = settings.ws_heartbeat_secs
    last_seen = loop.time()

    async def _heartbeat() -> None:
        while True:
            await asyncio.sleep(interval)
            if loop.time() - last_seen > 2 * interval:
                try:
                    await ws.close(code=CLOSE_HEARTBEAT_TIMEOUT, reason="heartbeat timeout")
                except Exception:  # noqa: S110 — socket already dead; main loop handles it
                    pass
                return
            try:
                await ws.send_json(PingFrame().model_dump(mode="json"))
            except Exception:
                return  # dead socket; the disconnect falls through to the main loop

    hb_task = asyncio.create_task(_heartbeat()) if interval > 0 else None
    try:
        while True:
            raw = await ws.receive_text()
            last_seen = loop.time()  # any received frame proves liveness
            if len(raw.encode()) > settings.ws_max_frame_bytes:
                await ws.close(code=CLOSE_PROTOCOL_ABUSE, reason="frame too large")
                break

            try:
                frame = client_frame_adapter.validate_json(raw)
            except ValidationError:
                malformed += 1
                if malformed >= MAX_MALFORMED_FRAMES:
                    await ws.close(code=CLOSE_PROTOCOL_ABUSE, reason="malformed frames")
                    break
                await _send_error(ws, "bad_frame", "Frame inválido.")
                continue

            # pong: only used to prove liveness (already recorded above).
            if isinstance(frame, PongFrame):
                continue

            # delivery ack: confirms receipt and releases the `delivered` to the
            # sender. Does not count against the token bucket (it is a response, not
            # a send) and is naturally bounded by the messages that reached this agent.
            if isinstance(frame, AckFrame):
                await _handle_ack(ws, slug, frame.message_id)
                continue

            # activity: transient 'responding…' signal, fanned out to panel
            # observers. Not persisted; bounded by the per-connection token bucket
            # only indirectly (it does not send messages).
            if isinstance(frame, ActivityFrame):
                await manager.broadcast_activity(
                    AgentActivityFrame(agent_id=slug, state=frame.state).model_dump(mode="json")
                )
                continue

            # autorespond report: an auditable run record. Attributed to the
            # authenticated `slug` (anti-spoof). Does not count against the token
            # bucket — it is bounded by the agent's actual auto-respond runs.
            if isinstance(frame, AutorespondReportFrame):
                await _handle_autorespond_report(ws, slug, frame)
                continue

            if not isinstance(frame, SendMessageFrame):
                await _send_error(ws, "bad_frame", "Frame inesperado.")
                continue

            if not bucket.allow():
                await _send_error(ws, "rate_limited", "Limite de mensagens excedido.")
                continue

            if frame.to.startswith("@"):
                await _handle_broadcast(ws, slug, frame)
            else:
                await _handle_send(ws, slug, frame)
    except WebSocketDisconnect:
        pass
    finally:
        if hb_task is not None:
            hb_task.cancel()
        removed = await manager.disconnect_agent(slug, ws)
        if removed:
            await manager.broadcast_presence(
                {"type": "presence", "agent_id": slug, "status": "offline"}
            )
            # clear any lingering 'responding…' indicator for this agent
            await manager.broadcast_activity(
                AgentActivityFrame(agent_id=slug, state="idle").model_dump(mode="json")
            )


async def _handle_send(ws: WebSocket, from_slug: str, frame: SendMessageFrame) -> None:
    session_factory = ws.app.state.session_factory

    # Writes protected by shield: a sender disconnect in the middle of the
    # operation must not leave the database/connection in an inconsistent state.
    async def _persist():
        async with session_factory() as session:
            return await _message_service(ws, session).send(
                from_slug,
                frame.to,
                frame.body,
                type=frame.msg_type,
                priority=frame.priority,
                in_reply_to=frame.in_reply_to,
            )

    try:
        msg = await asyncio.shield(_persist())
    except DomainError as exc:
        await _send_error(ws, exc.code, exc.detail)
        return

    # Pushes to the recipient; the `delivered` to the sender only goes out when
    # the recipient acks (at-least-once — see _handle_ack).
    await _dispatch(ws, msg)


async def _dispatch(ws: WebSocket, msg) -> bool:
    """Real-time delivery + mirror to observers, WITHOUT marking delivered.
    'Delivered' now means 'the recipient confirmed', not 'I pushed it down the
    pipe' — so delivered_at stays null until the ack. Returns whether the
    recipient's socket accepted (used by broadcast to list who is offline)."""
    manager: ConnectionManager = ws.app.state.manager
    accepted = await manager.send_to_agent(msg.to_agent, _message_payload(msg))
    await manager.notify_message(_message_payload(msg), msg.from_agent, msg.to_agent)
    return accepted


async def _handle_ack(ws: WebSocket, recipient_slug: str, message_id: int) -> None:
    """Recipient confirmed receipt: marks delivered, notifies the sender
    (`delivered`) and re-mirrors to observers with delivered_at filled in."""
    manager: ConnectionManager = ws.app.state.manager
    session_factory = ws.app.state.session_factory

    async def _ack():
        async with session_factory() as session:
            return await _message_service(ws, session).ack_delivery(recipient_slug, message_id)

    msg = await asyncio.shield(_ack())
    if msg is None:
        return  # ack from someone else, a no-op repeat, or for a nonexistent message

    await manager.send_to_agent(
        msg.from_agent,
        DeliveredFrame(message_id=msg.id, to=msg.to_agent).model_dump(mode="json"),
    )
    await manager.notify_message(_message_payload(msg), msg.from_agent, msg.to_agent)


async def _handle_autorespond_report(
    ws: WebSocket, slug: str, frame: AutorespondReportFrame
) -> None:
    """Persists an auto-respond run record under the authenticated agent. Shielded
    so a mid-write disconnect doesn't leave the row half-applied."""
    session_factory = ws.app.state.session_factory

    async def _persist():
        async with session_factory() as session:
            await build_autorespond_service(session).record_run(slug, frame.record)

    await asyncio.shield(_persist())


async def _handle_broadcast(ws: WebSocket, from_slug: str, frame: SendMessageFrame) -> None:
    """Fan-out @group/@all: dedicated rate limit + one DM per member."""
    state = ws.app.state
    session_factory = state.session_factory

    if not state.broadcast_limiter.allow(from_slug):
        await _send_error(ws, "rate_limited", "Limite de broadcasts por minuto excedido.")
        return
    if frame.in_reply_to is not None:
        await _send_error(ws, "invalid_input", "Broadcast não aceita in_reply_to.")
        return

    async def _persist():
        async with session_factory() as session:
            recipients = await build_group_service(session).resolve_recipients(frame.to, from_slug)
            return await _message_service(ws, session).send_broadcast(
                from_slug,
                frame.to,
                recipients,
                frame.body,
                type=frame.msg_type,
                priority=frame.priority,
            )

    try:
        sent, skipped = await asyncio.shield(_persist())
    except DomainError as exc:
        await _send_error(ws, exc.code, exc.detail)
        return

    offline: list[str] = []
    for msg in sent:
        if not await _dispatch(ws, msg):
            offline.append(msg.to_agent)

    result = BroadcastResultFrame(
        group=frame.to,
        sent=[m.to_agent for m in sent],
        skipped=skipped,
        offline=offline,
    )
    await ws.send_json(result.model_dump(mode="json"))


# ---------------------------------------------------------------- observers


async def _run_observer_connection(ws: WebSocket, hello: HelloFrame) -> None:
    state = ws.app.state
    manager: ConnectionManager = state.manager
    session_factory = state.session_factory

    async with session_factory() as session:
        auth = build_auth_service(session, state.settings)
        token = hello.jwt or ws.cookies.get(SESSION_COOKIE) or ""
        user = await auth.get_user_by_token(token)
        if user is None:
            await _send_error(ws, "auth_failed", "Sessão inválida ou expirada.")
            await ws.close(code=CLOSE_AUTH_FAIL, reason="auth failed")
            return
        owned = {a.slug for a in await build_agent_service(session).list_for_user(user)}

    conn = ObserverConn(ws=ws, user_id=user.id, role=user.role, owned_slugs=owned)
    await manager.add_observer(conn)
    ack = HelloAckFrame(
        agent_id=None,
        online=manager.online_slugs(),
        settings=None,
        pending=[],
        auto_responder_enabled=getattr(state, "auto_responder_enabled", True),
    )
    await ws.send_json(ack.model_dump(mode="json", by_alias=True))

    try:
        while True:
            # Observers do not send frames in the MVP — they just keep the connection alive
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.remove_observer(ws)


def _message_service(ws: WebSocket, session) -> MessageService:
    return build_message_service(session, ws.app.state.settings)
