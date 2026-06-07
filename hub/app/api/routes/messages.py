from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, get_group_service, get_message_service
from app.models.user import User, utcnow
from app.schemas.group import BroadcastResult
from app.schemas.message import PRIORITY_PATTERN, TYPE_PATTERN, ConversationPartner, MessageOut
from app.services.group_service import GroupService
from app.services.message_service import MessageService

router = APIRouter(prefix="/api/messages", tags=["messages"])


class SendMessageRequest(BaseModel):
    from_agent: str = Field(min_length=3, max_length=50, alias="from")
    to_agent: str = Field(min_length=3, max_length=50, alias="to")
    body: str = Field(min_length=1)
    type: str = Field(default="request", pattern=TYPE_PATTERN)
    priority: str = Field(default="normal", pattern=PRIORITY_PATTERN)
    in_reply_to: int | None = None

    model_config = {"populate_by_name": True}


@router.post("", response_model=MessageOut, status_code=201)
async def send_message(
    payload: SendMessageRequest,
    request: Request,
    user: User = Depends(get_current_user),
    svc: MessageService = Depends(get_message_service),
) -> MessageOut:
    """Painel: humano envia em nome do próprio agente. Entrega em tempo real
    espelha o fluxo do WS (delivered + espelho para observers)."""
    msg = await svc.send_as_user(
        user,
        payload.from_agent,
        payload.to_agent,
        payload.body,
        type=payload.type,
        priority=payload.priority,
        in_reply_to=payload.in_reply_to,
    )
    manager = request.app.state.manager
    out = MessageOut.model_validate(msg)
    frame = {"type": "message", "message": out.model_dump(mode="json", by_alias=True)}
    if await manager.send_to_agent(payload.to_agent, frame):
        await svc.mark_delivered([msg.id])
        out.delivered_at = utcnow()  # reflete o update na resposta
    await manager.notify_message(frame, payload.from_agent, payload.to_agent)
    return out


class BroadcastRequest(BaseModel):
    from_agent: str = Field(min_length=3, max_length=50, alias="from")
    group: str = Field(min_length=2, max_length=51, pattern=r"^@[a-z][a-z0-9-]*$")
    body: str = Field(min_length=1)
    type: str = Field(default="request", pattern=TYPE_PATTERN)
    priority: str = Field(default="normal", pattern=PRIORITY_PATTERN)

    model_config = {"populate_by_name": True}


@router.post("/broadcast", response_model=BroadcastResult, status_code=201)
async def broadcast(
    payload: BroadcastRequest,
    request: Request,
    user: User = Depends(get_current_user),
    svc: MessageService = Depends(get_message_service),
    groups: GroupService = Depends(get_group_service),
) -> BroadcastResult:
    """Painel: fan-out para @grupo ou @all em nome do próprio agente."""
    recipients = await groups.resolve_recipients(payload.group, payload.from_agent)
    sent, skipped = await svc.broadcast_as_user(
        user,
        payload.from_agent,
        payload.group,
        recipients,
        payload.body,
        type=payload.type,
        priority=payload.priority,
    )
    manager = request.app.state.manager
    delivered_ids: list[int] = []
    for msg in sent:
        out = MessageOut.model_validate(msg)
        frame = {"type": "message", "message": out.model_dump(mode="json", by_alias=True)}
        if await manager.send_to_agent(msg.to_agent, frame):
            delivered_ids.append(msg.id)
        await manager.notify_message(frame, payload.from_agent, msg.to_agent)
    if delivered_ids:
        await svc.mark_delivered(delivered_ids)
    return BroadcastResult(
        group=payload.group,
        sent=[m.to_agent for m in sent],
        skipped=skipped,
        message_ids=[m.id for m in sent],
    )


@router.get("/conversation", response_model=list[MessageOut])
async def conversation(
    a: str = Query(min_length=3, max_length=50),
    b: str = Query(min_length=3, max_length=50),
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    svc: MessageService = Depends(get_message_service),
) -> list[MessageOut]:
    return [MessageOut.model_validate(m) for m in await svc.conversation(user, a, b, limit)]


@router.get("/partners", response_model=list[ConversationPartner])
async def partners(
    agent: str = Query(min_length=3, max_length=50),
    user: User = Depends(get_current_user),
    svc: MessageService = Depends(get_message_service),
) -> list[ConversationPartner]:
    return await svc.partners(user, agent)
