"""Per-user inbox (Epic 02). Every route is scoped to the authenticated user."""

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import get_current_user, get_notification_service
from app.models.user import User
from app.schemas.notification import (
    NotificationOut,
    NotificationPatch,
    NotificationPrefs,
    NotificationPrefsPatch,
    SubscriptionOut,
    SubscriptionPut,
    UnreadCount,
)
from app.schemas.ws import NotificationReadFrame
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


@router.post("/read-all", response_model=UnreadCount)
async def read_all(
    request: Request,
    user: User = Depends(get_current_user),
    svc: NotificationService = Depends(get_notification_service),
) -> UnreadCount:
    await svc.mark_all_read(user)
    frame = NotificationReadFrame(ids="all", unread_count=0)
    await request.app.state.manager.notify_user(user.id, frame.model_dump(mode="json"))
    return UnreadCount(unread_count=0)


# Declared before /{notification_id} so "prefs" never tries to match the int
# path param (it would 422 instead of falling through).
@router.get("/prefs", response_model=NotificationPrefs)
async def get_prefs(
    user: User = Depends(get_current_user),
    svc: NotificationService = Depends(get_notification_service),
) -> NotificationPrefs:
    return NotificationPrefs(notify_level=svc.get_prefs(user))


@router.patch("/prefs", response_model=NotificationPrefs)
async def set_prefs(
    body: NotificationPrefsPatch,
    user: User = Depends(get_current_user),
    svc: NotificationService = Depends(get_notification_service),
) -> NotificationPrefs:
    return NotificationPrefs(notify_level=await svc.set_prefs(user, body.notify_level))


@router.put("/subscription", response_model=SubscriptionOut)
async def set_subscription(
    body: SubscriptionPut,
    user: User = Depends(get_current_user),
    svc: NotificationService = Depends(get_notification_service),
) -> SubscriptionOut:
    sub = await svc.set_subscription(user, body.subject_key, body.state)
    return SubscriptionOut.model_validate(sub)


@router.patch("/{notification_id}", response_model=NotificationOut)
async def triage(
    notification_id: int,
    body: NotificationPatch,
    request: Request,
    user: User = Depends(get_current_user),
    svc: NotificationService = Depends(get_notification_service),
) -> NotificationOut:
    notification = await svc.triage(user, notification_id, unread=body.unread, status=body.status)
    # Sync the badge + read-state to this user's other tabs/devices.
    frame = NotificationReadFrame(ids=[notification_id], unread_count=await svc.unread_count(user))
    await request.app.state.manager.notify_user(user.id, frame.model_dump(mode="json"))
    return NotificationOut.model_validate(notification)
