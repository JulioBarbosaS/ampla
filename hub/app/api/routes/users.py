from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.deps import get_auth_service, get_current_user
from app.models.user import User
from app.schemas.auth import AuditOut, PasswordResetIssued, RoleUpdate, UserOut
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/users", tags=["users"])


@router.post("/{user_id}/password-reset", response_model=PasswordResetIssued)
async def issue_password_reset(
    user_id: int,
    user: User = Depends(get_current_user),
    auth: AuthService = Depends(get_auth_service),
) -> PasswordResetIssued:
    """Admin issues a single-use reset link for a user (no email is sent — the
    admin hands the link over, like an invite)."""
    token, expires_at = await auth.issue_password_reset(user, user_id)
    return PasswordResetIssued(token=token, expires_at=expires_at)


@router.get("/{user_id}/avatar")
async def get_avatar(
    user_id: int,
    _user: User = Depends(get_current_user),
    auth: AuthService = Depends(get_auth_service),
) -> Response:
    """Serves a user's avatar bytes (any authenticated user — a profile photo is
    low-sensitivity). 404 when none, so the client falls back to the initial."""
    result = await auth.get_avatar(user_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    mime, data = result
    return Response(
        content=data,
        media_type=mime,
        headers={
            "Cache-Control": "private, max-age=60",
            "Content-Disposition": "inline",
            "X-Content-Type-Options": "nosniff",
        },
    )


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
