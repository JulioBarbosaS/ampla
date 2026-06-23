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
    build_approval_service,
    build_auth_service,
    build_autorespond_service,
    build_delegation_service,
    build_group_service,
    build_kanban_service,
    build_message_service,
    build_schedule_service,
)
from app.core.cookies import SESSION_COOKIE
from app.core.ratelimit import TokenBucket
from app.schemas.agent import AgentSettings
from app.schemas.kanban import CardCreate, CardMove, CardOut, CommentOut
from app.schemas.message import MessageOut
from app.schemas.ws import (
    AckFrame,
    ActivityFrame,
    AgentActivityFrame,
    ApprovalRequestFrame,
    AutorespondReportFrame,
    BroadcastResultFrame,
    DelegateFrame,
    DeliveredFrame,
    ErrorFrame,
    GroupInfo,
    HelloAckFrame,
    HelloFrame,
    KanbanActionFrame,
    KanbanDeltaFrame,
    MessageDeliveryFrame,
    PingFrame,
    PongFrame,
    ScheduledTaskReportFrame,
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

            # approval request: the agent drafted a reply but require_approval is
            # on. Persist it under the authenticated slug + notify the owner.
            if isinstance(frame, ApprovalRequestFrame):
                await _handle_approval_request(ws, slug, frame)
                continue

            # delegate: an interactive agent hands a task to another agent (Epic 04
            # · 4.4). It creates a real task message, so it counts against the
            # token bucket like any send.
            if isinstance(frame, DelegateFrame):
                if not bucket.allow():
                    await _send_error(ws, "rate_limited", "Limite de mensagens excedido.")
                    continue
                await _handle_delegate(ws, slug, frame)
                continue

            # kanban action: an interactive agent mutates a board (Epic 06 · 6.4).
            # It writes, so it counts against the token bucket. The hub re-checks
            # the per-agent capability — the daemon's claim is never trusted.
            if isinstance(frame, KanbanActionFrame):
                if not bucket.allow():
                    await _send_error(ws, "rate_limited", "Limite de mensagens excedido.")
                    continue
                await _handle_kanban_action(ws, slug, frame)
                continue

            # scheduled task report: the daemon ran a scheduled task and reports
            # its outcome (Epic 08 · 8.4). Recorded under the authenticated slug.
            if isinstance(frame, ScheduledTaskReportFrame):
                await _handle_scheduled_task_report(ws, slug, frame)
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
    """Persists an auto-respond run record under the authenticated agent and, if
    the outcome warrants it, escalates the trigger message to the owner's Inbox
    (Epic 04 · 4.3). Shielded so a mid-write disconnect doesn't half-apply it."""
    state = ws.app.state
    session_factory = state.session_factory

    async def _persist():
        async with session_factory() as session:
            await build_autorespond_service(session, state.settings, state.manager).record_run(
                slug, frame.record
            )

    await asyncio.shield(_persist())


async def _handle_scheduled_task_report(
    ws: WebSocket, slug: str, frame: ScheduledTaskReportFrame
) -> None:
    """Records a scheduled run's outcome under the authenticated agent (Epic 08 ·
    8.4). The service verifies the schedule belongs to that agent (anti-spoof).
    Shielded so a mid-write disconnect doesn't half-apply it."""
    state = ws.app.state

    async def _persist():
        async with state.session_factory() as session:
            await build_schedule_service(session, state.settings).record_report(
                slug, frame.schedule_id, frame.status, frame.summary
            )

    await asyncio.shield(_persist())


async def _handle_approval_request(ws: WebSocket, slug: str, frame: ApprovalRequestFrame) -> None:
    """Persists a pending approval under the authenticated agent and notifies its
    owner. Shielded so a mid-write disconnect doesn't half-apply the row."""
    state = ws.app.state
    session_factory = state.session_factory

    async def _persist():
        async with session_factory() as session:
            await build_approval_service(session, state.settings, state.manager).create_request(
                slug, frame.to, frame.draft_body, frame.trigger_message_id
            )

    await asyncio.shield(_persist())


async def _handle_delegate(ws: WebSocket, slug: str, frame: DelegateFrame) -> None:
    """An interactive agent delegates a task to another agent (Epic 04 · 4.4).
    The service sends the task AS the authenticated delegator (allowlist + routing
    enforced) and records the delegation. Shielded so a mid-write disconnect
    doesn't half-apply it. A domain error (self-delegate, too many open) goes back
    as an error frame."""
    state = ws.app.state
    session_factory = state.session_factory

    async def _persist():
        async with session_factory() as session:
            return await build_delegation_service(session, state.settings, state.manager).delegate(
                slug, frame.to, frame.task, frame.context
            )

    try:
        await asyncio.shield(_persist())
    except DomainError as exc:
        await _send_error(ws, exc.code, exc.detail)


async def _handle_kanban_action(ws: WebSocket, slug: str, frame: KanbanActionFrame) -> None:
    """An interactive agent acts on a board (Epic 06 · 6.4). Attributed to the
    AUTHENTICATED `slug`; the service enforces the per-agent capability (§6.3),
    so a daemon with an insufficient role gets an error frame even if it tries.
    On success, broadcasts a `kanban_delta` to the board's authorized observers
    (§6.5). Shielded so a mid-write disconnect doesn't half-apply it."""
    state = ws.app.state
    session_factory = state.session_factory
    manager: ConnectionManager = state.manager

    async def _apply() -> tuple[dict, int, bool]:
        async with session_factory() as session:
            svc = build_kanban_service(session, state.settings, state.manager)
            payload = frame.payload
            if frame.op == "create_card":
                card = await svc.agent_create_card(
                    slug, frame.board_id, CardCreate.model_validate(payload)
                )
                board_id = card.board_id
                delta = KanbanDeltaFrame(
                    board_id=board_id, op="card_created", card=CardOut.model_validate(card)
                )
            elif frame.op == "move_card":
                mv = CardMove.model_validate({k: v for k, v in payload.items() if k != "card_id"})
                card = await svc.agent_move_card(
                    slug,
                    int(payload["card_id"]),
                    mv.to_column_id,
                    before_id=mv.before_id,
                    after_id=mv.after_id,
                    expected_version=mv.expected_version,
                )
                board_id = card.board_id
                delta = KanbanDeltaFrame(
                    board_id=board_id, op="card_moved", card=CardOut.model_validate(card)
                )
            else:  # comment
                comment = await svc.agent_comment(
                    slug, int(payload["card_id"]), str(payload.get("body", ""))
                )
                board = await svc.board_of_card(comment.card_id)
                board_id = board.id if board else frame.board_id
                delta = KanbanDeltaFrame(
                    board_id=board_id,
                    op="comment_added",
                    comment=CommentOut.model_validate(comment),
                )
            board = await svc.get_board_raw(board_id)
            owner_id = board.owner_id if board else 0
            is_team = bool(board and board.visibility == "team")
            # Private boards still reach the people they were shared with (Epic 10).
            member_ids = set() if is_team else set(await svc.board_member_ids(board_id))
            return delta.model_dump(mode="json", by_alias=True), owner_id, is_team, member_ids

    try:
        payload, owner_id, is_team, member_ids = await asyncio.shield(_apply())
    except DomainError as exc:
        await _send_error(ws, exc.code, exc.detail)
        return
    except (ValidationError, KeyError, TypeError, ValueError):
        await _send_error(ws, "invalid_input", "Payload de ação inválido.")
        return

    await manager.notify_board(payload, owner_id=owner_id, is_team=is_team, member_ids=member_ids)


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
    return build_message_service(session, ws.app.state.settings, ws.app.state.manager)
