"""Reusable guardrail presets (Epic 04 · 4.1). Apply lives on the agents router
(POST /api/agents/{slug}/apply-preset)."""

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import get_current_user, get_preset_service
from app.models.user import User
from app.schemas.preset import PresetCreate, PresetOut, PresetUpdate
from app.services.preset_service import PresetService

router = APIRouter(prefix="/api/guardrail-presets", tags=["presets"])


@router.get("", response_model=list[PresetOut])
async def list_presets(
    user: User = Depends(get_current_user),
    svc: PresetService = Depends(get_preset_service),
) -> list[PresetOut]:
    return [PresetOut.model_validate(p) for p in await svc.list(user)]


@router.post("", response_model=PresetOut, status_code=201)
async def create_preset(
    body: PresetCreate,
    user: User = Depends(get_current_user),
    svc: PresetService = Depends(get_preset_service),
) -> PresetOut:
    return PresetOut.model_validate(await svc.create(user, body))


@router.patch("/{preset_id}", response_model=PresetOut)
async def update_preset(
    preset_id: int,
    body: PresetUpdate,
    user: User = Depends(get_current_user),
    svc: PresetService = Depends(get_preset_service),
) -> PresetOut:
    return PresetOut.model_validate(await svc.update(user, preset_id, body))


@router.delete("/{preset_id}", status_code=204)
async def delete_preset(
    preset_id: int,
    user: User = Depends(get_current_user),
    svc: PresetService = Depends(get_preset_service),
) -> Response:
    await svc.delete(user, preset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
