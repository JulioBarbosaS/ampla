from fastapi import APIRouter, Depends, Query

from app.api.deps import get_auth_service, get_current_user
from app.models.user import User
from app.schemas.auth import AuditOut, RoleUpdate, UserOut
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/audit", response_model=list[AuditOut])
async def audit_log(
    limit: int = Query(default=100, ge=1, le=500),
    user: User = Depends(get_current_user),
    auth: AuthService = Depends(get_auth_service),
) -> list[AuditOut]:
    return [AuditOut.model_validate(e) for e in await auth.list_audit(user, limit)]


@router.get("", response_model=list[UserOut])
async def list_users(
    user: User = Depends(get_current_user),
    auth: AuthService = Depends(get_auth_service),
) -> list[UserOut]:
    return [UserOut.model_validate(u) for u in await auth.list_users(user)]


@router.patch("/{user_id}/role", response_model=UserOut)
async def set_role(
    user_id: int,
    body: RoleUpdate,
    user: User = Depends(get_current_user),
    auth: AuthService = Depends(get_auth_service),
) -> UserOut:
    return UserOut.model_validate(await auth.set_role(user, user_id, body.role))
