"""Instance-wide admin controls. Admin-only (require_admin)."""

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import (
    get_admin_service,
    get_autorespond_service,
    get_metrics_service,
    require_admin,
)
from app.models.user import User
from app.schemas.admin import KillSwitchState, KillSwitchUpdate
from app.schemas.autorespond import AutorespondRunOut
from app.schemas.metrics import MetricsOut
from app.schemas.ws import KillSwitchFrame
from app.services.admin_service import AdminService
from app.services.autorespond_service import AutorespondService
from app.services.metrics_service import MetricsService

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


@router.get("/autorespond-runs", response_model=list[AutorespondRunOut])
async def all_autorespond_runs(
    limit: int = Query(default=50, ge=1, le=200),
    _admin: User = Depends(require_admin),
    ar_svc: AutorespondService = Depends(get_autorespond_service),
) -> list[AutorespondRunOut]:
    """Instance-wide transcript across every agent (admin only)."""
    return [AutorespondRunOut.model_validate(r) for r in await ar_svc.list_all(limit)]


@router.get("/metrics", response_model=MetricsOut)
async def metrics(
    days: int = Query(default=7, ge=1, le=90),
    _admin: User = Depends(require_admin),
    svc: MetricsService = Depends(get_metrics_service),
) -> MetricsOut:
    """Instance observability: windowed auto-respond cost/result roll-up, a daily
    series, message throughput and audit event families (admin only, read-only)."""
    return await svc.snapshot(days)
