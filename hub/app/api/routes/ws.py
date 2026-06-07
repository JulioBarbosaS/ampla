"""Endpoint WebSocket: daemons de agentes e observers do painel.

Camada de transporte: faz parse/serialização de frames e orquestra
services + ConnectionManager. Nunca toca repositories diretamente —
services são construídos via fábricas locais com sessão por operação.

Segurança (docs/ARCHITECTURE.md · Ameaça 3): hello obrigatório em 10s,
limite de frame, token bucket por conexão, desconexão após frames
malformados repetidos.
"""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.api.deps import (
    build_agent_service,
    build_auth_service,
    build_group_service,
    build_message_service,
)
from app.core.ratelimit import TokenBucket
from app.models.user import utcnow
from app.schemas.agent import AgentSettings
from app.schemas.message import MessageOut
from app.schemas.ws import (
    BroadcastResultFrame,
    DeliveredFrame,
    ErrorFrame,
    GroupInfo,
    HelloAckFrame,
    HelloFrame,
    MessageDeliveryFrame,
    SendMessageFrame,
    client_frame_adapter,
)
from app.services.errors import DomainError
from app.services.message_service import MessageService
from app.ws.connection_manager import ConnectionManager, ObserverConn

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_MALFORMED_FRAMES = 5

# Códigos de fechamento próprios (4xxx = aplicação)
CLOSE_BAD_HELLO = 4400
CLOSE_AUTH_FAIL = 4401
CLOSE_PROTOCOL_ABUSE = 4429


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

    # ---- hello obrigatório dentro do timeout ----
    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=settings.ws_hello_timeout_secs)
    except WebSocketDisconnect:
        return  # cliente desistiu antes do hello
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
    elif hello.jwt:
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

    # autenticação + snapshot inicial (sessão curta)
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
    )
    await ws.send_json(ack.model_dump(mode="json", by_alias=True))

    if pending:

        async def _flush() -> None:
            async with session_factory() as session:
                await _message_service(ws, session).mark_delivered([m.id for m in pending])

        # shield: desconexão no meio do flush não pode interromper a escrita
        await asyncio.shield(_flush())

    bucket = TokenBucket(settings.ws_messages_per_minute)
    malformed = 0
    try:
        while True:
            raw = await ws.receive_text()
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
        removed = await manager.disconnect_agent(slug, ws)
        if removed:
            await manager.broadcast_presence(
                {"type": "presence", "agent_id": slug, "status": "offline"}
            )


async def _handle_send(ws: WebSocket, from_slug: str, frame: SendMessageFrame) -> None:
    session_factory = ws.app.state.session_factory

    # Escritas protegidas por shield: desconexão do remetente no meio da
    # operação não pode deixar o banco/conexão em estado inconsistente.
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

    delivered = await _deliver(ws, msg)
    if delivered:
        await ws.send_json(DeliveredFrame(message_id=msg.id, to=frame.to).model_dump(mode="json"))


async def _deliver(ws: WebSocket, msg) -> bool:
    """Entrega em tempo real + marca delivered + espelha para observers."""
    manager: ConnectionManager = ws.app.state.manager
    session_factory = ws.app.state.session_factory

    # Marca delivered no objeto ANTES de serializar, para que o frame entregue
    # (e o espelho aos observers) reflita o timestamp — e não delivered_at:null.
    msg.delivered_at = utcnow()
    delivered = await manager.send_to_agent(msg.to_agent, _message_payload(msg))
    if delivered:

        async def _mark() -> None:
            async with session_factory() as session:
                await _message_service(ws, session).mark_delivered([msg.id])

        await asyncio.shield(_mark())
    else:
        msg.delivered_at = None  # destinatário offline: fica pendente

    await manager.notify_message(_message_payload(msg), msg.from_agent, msg.to_agent)
    return delivered


async def _handle_broadcast(ws: WebSocket, from_slug: str, frame: SendMessageFrame) -> None:
    """Fan-out @grupo/@all: rate limit próprio + uma DM por membro."""
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
        if not await _deliver(ws, msg):
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
        user = await auth.get_user_by_token(hello.jwt or "")
        if user is None:
            await _send_error(ws, "auth_failed", "Sessão inválida ou expirada.")
            await ws.close(code=CLOSE_AUTH_FAIL, reason="auth failed")
            return
        owned = {a.slug for a in await build_agent_service(session).list_for_user(user)}

    conn = ObserverConn(ws=ws, user_id=user.id, role=user.role, owned_slugs=owned)
    await manager.add_observer(conn)
    ack = HelloAckFrame(agent_id=None, online=manager.online_slugs(), settings=None, pending=[])
    await ws.send_json(ack.model_dump(mode="json", by_alias=True))

    try:
        while True:
            # Observers não enviam frames no MVP — só mantêm a conexão viva
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.remove_observer(ws)


def _message_service(ws: WebSocket, session) -> MessageService:
    return build_message_service(session, ws.app.state.settings)
