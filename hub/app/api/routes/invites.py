from fastapi import APIRouter, Depends

from app.api.deps import get_auth_service, get_current_user
from app.models.user import User
from app.schemas.invite import InviteOut
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/invites", tags=["invites"])


@router.post("", response_model=InviteOut, status_code=201)
async def create_invite(
    user: User = Depends(get_current_user),
    auth: AuthService = Depends(get_auth_service),
) -> InviteOut:
    invite = await auth.create_invite(user)
    return InviteOut.model_validate(invite)


@router.get("", response_model=list[InviteOut])
async def list_invites(
    user: User = Depends(get_current_user),
    auth: AuthService = Depends(get_auth_service),
) -> list[InviteOut]:
    return [InviteOut.model_validate(i) for i in await auth.list_invites(user)]
