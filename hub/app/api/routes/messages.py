from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, get_message_service
from app.models.user import User, utcnow
from app.schemas.message import ConversationPartner, MessageOut
from app.services.message_service import MessageService

router = APIRouter(prefix="/api/messages", tags=["messages"])


class SendMessageRequest(BaseModel):
    from_agent: str = Field(min_length=3, max_length=50, alias="from")
    to_agent: str = Field(min_length=3, max_length=50, alias="to")
    body: str = Field(min_length=1)

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
    msg = await svc.send_as_user(user, payload.from_agent, payload.to_agent, payload.body)
    manager = request.app.state.manager
    out = MessageOut.model_validate(msg)
    frame = {"type": "message", "message": out.model_dump(mode="json", by_alias=True)}
    if await manager.send_to_agent(payload.to_agent, frame):
        await svc.mark_delivered([msg.id])
        out.delivered_at = utcnow()  # reflete o update na resposta
    await manager.notify_message(frame, payload.from_agent, payload.to_agent)
    return out


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
