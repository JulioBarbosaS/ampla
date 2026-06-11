"""Instance-wide admin controls. Admin-only (require_admin)."""

from fastapi import APIRouter, Depends, Request

from app.api.deps import get_admin_service, require_admin
from app.models.user import User
from app.schemas.admin import KillSwitchState, KillSwitchUpdate
from app.schemas.ws import KillSwitchFrame
from app.services.admin_service import AdminService

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/kill-switch", response_model=KillSwitchState)
async def get_kill_switch(
    _admin: User = Depends(require_admin),
    svc: AdminService = Depends(get_admin_service),
) -> KillSwitchState:
    return KillSwitchState(auto_responder_enabled=await svc.get_kill_switch())


@router.post("/kill-switch", response_model=KillSwitchState)
async def set_kill_switch(
    body: KillSwitchUpdate,
    request: Request,
    admin: User = Depends(require_admin),
    svc: AdminService = Depends(get_admin_service),
) -> KillSwitchState:
    enabled = await svc.set_kill_switch(admin, body.enabled)
    # Cache on app.state so daemon hello_ack reflects it without a DB read, then
    # broadcast the flip to every connected daemon + observer in real time.
    request.app.state.auto_responder_enabled = enabled
    frame = KillSwitchFrame(auto_responder_enabled=enabled)
    await request.app.state.manager.broadcast_kill_switch(frame.model_dump(mode="json"))
    return KillSwitchState(auto_responder_enabled=enabled)
