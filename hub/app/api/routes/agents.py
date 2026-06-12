from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import (
    get_agent_service,
    get_approval_service,
    get_autorespond_service,
    get_current_user,
)
from app.models.user import User
from app.schemas.agent import (
    AgentCreate,
    AgentKeyCreate,
    AgentKeyCreated,
    AgentKeyOut,
    AgentOut,
    AgentSettingsUpdate,
    DirectoryEntry,
)
from app.schemas.approval import ApprovalOut
from app.schemas.autorespond import AutorespondRunOut
from app.schemas.ws import SettingsUpdateFrame
from app.services.agent_service import AgentService
from app.services.approval_service import ApprovalService
from app.services.autorespond_service import AutorespondService

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.post("", response_model=AgentOut, status_code=201)
async def create_agent(
    body: AgentCreate,
    user: User = Depends(get_current_user),
    svc: AgentService = Depends(get_agent_service),
) -> AgentOut:
    return AgentOut.model_validate(await svc.create(user, body))


@router.get("", response_model=list[AgentOut])
async def list_my_agents(
    user: User = Depends(get_current_user),
    svc: AgentService = Depends(get_agent_service),
) -> list[AgentOut]:
    return [AgentOut.model_validate(a) for a in await svc.list_for_user(user)]


@router.get("/directory", response_model=list[DirectoryEntry])
async def directory(
    request: Request,
    _user: User = Depends(get_current_user),
    svc: AgentService = Depends(get_agent_service),
) -> list[DirectoryEntry]:
    manager = request.app.state.manager
    return [
        DirectoryEntry(slug=a.slug, display_name=a.display_name, online=manager.is_online(a.slug))
        for a in await svc.list_all()
    ]


@router.get("/{slug}", response_model=AgentOut)
async def get_agent(
    slug: str,
    user: User = Depends(get_current_user),
    svc: AgentService = Depends(get_agent_service),
) -> AgentOut:
    return AgentOut.model_validate(await svc.get_owned(user, slug))


@router.patch("/{slug}/settings", response_model=AgentOut)
async def update_settings(
    slug: str,
    body: AgentSettingsUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    svc: AgentService = Depends(get_agent_service),
) -> AgentOut:
    agent = await svc.update_settings(user, slug, body)
    # Real-time push to the daemon (docs/ARCHITECTURE.md · WS protocol)
    frame = SettingsUpdateFrame(settings=svc.settings_of(agent))
    await request.app.state.manager.send_settings_update(slug, frame.model_dump(mode="json"))
    return AgentOut.model_validate(agent)


@router.get("/{slug}/autorespond-runs", response_model=list[AutorespondRunOut])
async def autorespond_runs(
    slug: str,
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    svc: AgentService = Depends(get_agent_service),
    ar_svc: AutorespondService = Depends(get_autorespond_service),
) -> list[AutorespondRunOut]:
    await svc.get_owned(user, slug)  # owner/admin authz (raises otherwise)
    runs = await ar_svc.list_for_agent(slug, limit)
    return [AutorespondRunOut.model_validate(r) for r in runs]


@router.get("/{slug}/approvals", response_model=list[ApprovalOut])
async def list_approvals(
    slug: str,
    status: str | None = Query(default=None, pattern=r"^(pending|approved|rejected|edited)$"),
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(get_current_user),
    svc: ApprovalService = Depends(get_approval_service),
) -> list[ApprovalOut]:
    # ApprovalService enforces owner/admin authz on the agent.
    items = await svc.list_for_agent(user, slug, status=status, limit=limit)
    return [ApprovalOut.model_validate(a) for a in items]


@router.post("/{slug}/keys", response_model=AgentKeyCreated, status_code=201)
async def create_key(
    slug: str,
    body: AgentKeyCreate,
    user: User = Depends(get_current_user),
    svc: AgentService = Depends(get_agent_service),
) -> AgentKeyCreated:
    key, plaintext = await svc.create_key(user, slug, body.label)
    return AgentKeyCreated(id=key.id, label=key.label, key=plaintext)


@router.get("/{slug}/keys", response_model=list[AgentKeyOut])
async def list_keys(
    slug: str,
    user: User = Depends(get_current_user),
    svc: AgentService = Depends(get_agent_service),
) -> list[AgentKeyOut]:
    return [AgentKeyOut.model_validate(k) for k in await svc.list_keys(user, slug)]


@router.delete("/{slug}/keys/{key_id}", response_model=AgentKeyOut)
async def revoke_key(
    slug: str,
    key_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    svc: AgentService = Depends(get_agent_service),
) -> AgentKeyOut:
    key = await svc.revoke_key(user, slug, key_id)
    # Revocation drops the WS immediately (Threat 2). The connection may be using
    # another valid key — in that case the daemon reconnects on its own.
    manager = request.app.state.manager
    if await manager.kick_agent(slug, reason="key_revoked"):
        # the dropped loop does not emit offline (slug already removed), so broadcast here
        await manager.broadcast_presence(
            {"type": "presence", "agent_id": slug, "status": "offline"}
        )
    return AgentKeyOut.model_validate(key)
