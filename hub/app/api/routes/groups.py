from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_group_service
from app.models.user import User
from app.schemas.group import GroupCreate, GroupMemberAdd, GroupOut
from app.services.group_service import GroupService

router = APIRouter(prefix="/api/groups", tags=["groups"])


@router.post("", response_model=GroupOut, status_code=201)
async def create_group(
    body: GroupCreate,
    user: User = Depends(get_current_user),
    svc: GroupService = Depends(get_group_service),
) -> GroupOut:
    group = await svc.create(user, body)
    return GroupOut.model_validate(group)


@router.get("", response_model=list[GroupOut])
async def list_groups(
    _user: User = Depends(get_current_user),
    svc: GroupService = Depends(get_group_service),
) -> list[GroupOut]:
    return [
        GroupOut(
            slug=group.slug,
            display_name=group.display_name,
            created_by=group.created_by,
            created_at=group.created_at,
            members=members,
        )
        for group, members in await svc.list_with_members()
    ]


@router.delete("/{slug}", status_code=204)
async def delete_group(
    slug: str,
    user: User = Depends(get_current_user),
    svc: GroupService = Depends(get_group_service),
) -> None:
    await svc.delete(user, slug)


@router.post("/{slug}/members", status_code=204)
async def add_member(
    slug: str,
    body: GroupMemberAdd,
    user: User = Depends(get_current_user),
    svc: GroupService = Depends(get_group_service),
) -> None:
    await svc.add_member(user, slug, body.agent)


@router.delete("/{slug}/members/{agent}", status_code=204)
async def remove_member(
    slug: str,
    agent: str,
    user: User = Depends(get_current_user),
    svc: GroupService = Depends(get_group_service),
) -> None:
    await svc.remove_member(user, slug, agent)
