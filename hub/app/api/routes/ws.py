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

from app.core.ratelimit import TokenBucket
from app.repositories.agent_repo import AgentRepository
from app.repositories.audit_repo import AuditRepository
from app.repositories.invite_repo import InviteRepository
from app.repositories.message_repo import MessageRepository
from app.repositories.user_repo import UserRepository
from app.schemas.agent import AgentSettings
from app.schemas.message import MessageOut
from app.schemas.ws import (
    DeliveredFrame,
    ErrorFrame,
    HelloAckFrame,
    HelloFrame,
    MessageDeliveryFrame,
    SendMessageFrame,
    client_frame_adapter,
)
from app.services.agent_service import AgentService
from app.services.auth_service import AuthService
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
        raw = await asyncio.wait_for(
            ws.receive_text(), timeout=settings.ws_hello_timeout_secs
        )
    except WebSocketDisconnect:
        return  # cliente desistiu antes do hello
    except (TimeoutError, asyncio.TimeoutError):
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
        agent_svc = AgentService(AgentRepository(session), AuditRepository(session))
        agent = await agent_svc.authenticate_key(slug, hello.key or "")
        if agent is None:
            await AuditRepository(session).record("ws_auth_fail", actor=slug or "?")
            await _send_error(ws, "auth_failed", "Chave inválida ou revogada.")
            await ws.close(code=CLOSE_AUTH_FAIL, reason="auth failed")
            return
        msg_svc = _build_message_service(ws, session)
        pending = await msg_svc.pending_for(slug)
        agent_settings = AgentSettings.model_validate(agent)

    await manager.connect_agent(slug, ws)
    await manager.broadcast_presence(
        {"type": "presence", "agent_id": slug, "status": "online"}
    )

    ack = HelloAckFrame(
        agent_id=slug,
        online=manager.online_slugs(),
        settings=agent_settings,
        pending=[MessageOut.model_validate(m) for m in pending],
    )
    await ws.send_json(ack.model_dump(mode="json", by_alias=True))

    if pending:

        async def _flush() -> None:
            async with session_factory() as session:
                await _build_message_service(ws, session).mark_delivered(
                    [m.id for m in pending]
                )

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
    manager: ConnectionManager = ws.app.state.manager
    session_factory = ws.app.state.session_factory

    # Escritas protegidas por shield: desconexão do remetente no meio da
    # operação não pode deixar o banco/conexão em estado inconsistente.
    async def _persist():
        async with session_factory() as session:
            return await _build_message_service(ws, session).send(
                from_slug, frame.to, frame.body
            )

    try:
        msg = await asyncio.shield(_persist())
    except DomainError as exc:
        await _send_error(ws, exc.code, exc.detail)
        return

    payload = _message_payload(msg)
    delivered = await manager.send_to_agent(frame.to, payload)
    if delivered:

        async def _mark() -> None:
            async with session_factory() as session:
                await _build_message_service(ws, session).mark_delivered([msg.id])

        await asyncio.shield(_mark())

    await manager.notify_message(payload, from_slug, frame.to)
    if delivered:
        await ws.send_json(
            DeliveredFrame(message_id=msg.id, to=frame.to).model_dump(mode="json")
        )


# ---------------------------------------------------------------- observers


async def _run_observer_connection(ws: WebSocket, hello: HelloFrame) -> None:
    state = ws.app.state
    manager: ConnectionManager = state.manager
    session_factory = state.session_factory

    async with session_factory() as session:
        auth = AuthService(
            UserRepository(session),
            InviteRepository(session),
            AuditRepository(session),
            state.settings,
        )
        user = await auth.get_user_by_token(hello.jwt or "")
        if user is None:
            await _send_error(ws, "auth_failed", "Sessão inválida ou expirada.")
            await ws.close(code=CLOSE_AUTH_FAIL, reason="auth failed")
            return
        owned = {a.slug for a in await AgentRepository(session).list_by_user(user.id)}

    conn = ObserverConn(ws=ws, user_id=user.id, role=user.role, owned_slugs=owned)
    await manager.add_observer(conn)
    ack = HelloAckFrame(
        agent_id=None, online=manager.online_slugs(), settings=None, pending=[]
    )
    await ws.send_json(ack.model_dump(mode="json", by_alias=True))

    try:
        while True:
            # Observers não enviam frames no MVP — só mantêm a conexão viva
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.remove_observer(ws)


def _build_message_service(ws: WebSocket, session) -> MessageService:
    return MessageService(
        messages=MessageRepository(session),
        agents=AgentRepository(session),
        audit=AuditRepository(session),
        settings=ws.app.state.settings,
    )
