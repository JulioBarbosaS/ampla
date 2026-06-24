from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, get_group_service, get_message_service
from app.models.user import User
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
    """Panel: a human sends on behalf of their own agent. Real-time delivery
    mirrors the WS flow (delivered + mirror to observers)."""
    if not request.app.state.message_limiter.allow(str(user.id)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Limite de mensagens excedido.",
        )
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
    # Push in real time + mirror to observers, but DON'T mark delivered here:
    # `delivered_at` means the recipient confirmed (at-least-once), driven by the
    # recipient's `ack` — same contract as the WS send path (ws.py `_dispatch`).
    # Marking on push would lose a message if the daemon dies before processing it.
    await manager.send_to_agent(payload.to_agent, frame)
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
    """Panel: fan-out to @group or @all on behalf of the agent's own owner."""
    # Authorize the sender BEFORE touching the per-agent broadcast limiter, so a
    # client can't exhaust another agent's bucket by naming an agent it doesn't
    # own (anti-spoof). `send_message` already keys its limiter on the user.
    await svc.assert_sender_owned(user, payload.from_agent)
    if not request.app.state.broadcast_limiter.allow(payload.from_agent):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Limite de broadcasts por minuto excedido.",
        )
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
    # Real-time push + observer mirror; delivery is confirmed by each recipient's
    # `ack` (at-least-once), not by the push — same contract as the WS path.
    for msg in sent:
        out = MessageOut.model_validate(msg)
        frame = {"type": "message", "message": out.model_dump(mode="json", by_alias=True)}
        await manager.send_to_agent(msg.to_agent, frame)
        await manager.notify_message(frame, payload.from_agent, msg.to_agent)
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
