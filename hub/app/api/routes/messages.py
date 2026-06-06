from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user, get_message_service
from app.models.user import User
from app.schemas.message import ConversationPartner, MessageOut
from app.services.message_service import MessageService

router = APIRouter(prefix="/api/messages", tags=["messages"])


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
