"""Scheduled agent task REST API (Epic 08). Thin routes: authenticate the user
and delegate to ScheduleService, which owns ownership authz and (kind, spec)
validation (docs/ARCHITECTURE.md layer rules). The engine fires due schedules;
these endpoints only manage them."""

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_schedule_service
from app.models.user import User
from app.schemas.schedule import ScheduleCreate, ScheduleOut, ScheduleUpdate
from app.services.schedule_service import ScheduleService

router = APIRouter(prefix="/api", tags=["schedules"])


@router.get("/agents/{agent_slug}/schedules", response_model=list[ScheduleOut])
async def list_schedules(
    agent_slug: str,
    user: User = Depends(get_current_user),
    svc: ScheduleService = Depends(get_schedule_service),
) -> list[ScheduleOut]:
    return [ScheduleOut.model_validate(s) for s in await svc.list_for_agent(user, agent_slug)]


@router.post("/agents/{agent_slug}/schedules", response_model=ScheduleOut, status_code=201)
async def create_schedule(
    agent_slug: str,
    body: ScheduleCreate,
    user: User = Depends(get_current_user),
    svc: ScheduleService = Depends(get_schedule_service),
) -> ScheduleOut:
    return ScheduleOut.model_validate(await svc.create(user, agent_slug, body))


@router.get("/schedules/{schedule_id}", response_model=ScheduleOut)
async def get_schedule(
    schedule_id: int,
    user: User = Depends(get_current_user),
    svc: ScheduleService = Depends(get_schedule_service),
) -> ScheduleOut:
    return ScheduleOut.model_validate(await svc.get(user, schedule_id))


@router.patch("/schedules/{schedule_id}", response_model=ScheduleOut)
async def update_schedule(
    schedule_id: int,
    body: ScheduleUpdate,
    user: User = Depends(get_current_user),
    svc: ScheduleService = Depends(get_schedule_service),
) -> ScheduleOut:
    return ScheduleOut.model_validate(await svc.update(user, schedule_id, body))


@router.delete("/schedules/{schedule_id}", status_code=204)
async def delete_schedule(
    schedule_id: int,
    user: User = Depends(get_current_user),
    svc: ScheduleService = Depends(get_schedule_service),
) -> None:
    await svc.delete(user, schedule_id)


@router.post("/schedules/{schedule_id}/run", response_model=ScheduleOut)
async def run_schedule_now(
    schedule_id: int,
    user: User = Depends(get_current_user),
    svc: ScheduleService = Depends(get_schedule_service),
) -> ScheduleOut:
    return ScheduleOut.model_validate(await svc.run_now(user, schedule_id))
