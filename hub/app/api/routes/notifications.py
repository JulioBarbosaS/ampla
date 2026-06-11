"""Per-user inbox (Epic 02). Every route is scoped to the authenticated user."""

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user, get_notification_service
from app.models.user import User
from app.schemas.notification import NotificationOut, NotificationPatch, UnreadCount
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
async def list_notifications(
    status: str | None = Query(default=None, pattern=r"^(inbox|saved|done)$"),
    unread: bool | None = None,
    reason: str | None = Query(default=None, max_length=24),
    agent: str | None = Query(default=None, max_length=60),
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(get_current_user),
    svc: NotificationService = Depends(get_notification_service),
) -> list[NotificationOut]:
    items = await svc.list(
        user, status=status, unread=unread, reason=reason, agent_slug=agent, limit=limit
    )
    return [NotificationOut.model_validate(n) for n in items]


@router.get("/unread-count", response_model=UnreadCount)
async def unread_count(
    user: User = Depends(get_current_user),
    svc: NotificationService = Depends(get_notification_service),
) -> UnreadCount:
    return UnreadCount(unread_count=await svc.unread_count(user))


@router.patch("/{notification_id}", response_model=NotificationOut)
async def triage(
    notification_id: int,
    body: NotificationPatch,
    user: User = Depends(get_current_user),
    svc: NotificationService = Depends(get_notification_service),
) -> NotificationOut:
    notification = await svc.triage(user, notification_id, unread=body.unread, status=body.status)
    return NotificationOut.model_validate(notification)
