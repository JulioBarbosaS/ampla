"""Agent groups: creation, membership (owner opt-in) and recipient
resolution for broadcast (@group / @all)."""

from app.models.group import Group
from app.models.user import User
from app.repositories.agent_repo import AgentRepository
from app.repositories.audit_repo import AuditRepository
from app.repositories.group_repo import GroupRepository
from app.schemas.agent import RESERVED_SLUGS
from app.schemas.group import GroupCreate
from app.services.errors import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
)


class GroupService:
    def __init__(
        self, groups: GroupRepository, agents: AgentRepository, audit: AuditRepository
    ) -> None:
        self._groups = groups
        self._agents = agents
        self._audit = audit

    async def create(self, actor: User, data: GroupCreate) -> Group:
        if data.slug in RESERVED_SLUGS:
            raise InvalidInputError(f"{data.slug!r} é reservado para o broadcast embutido.")
        if await self._groups.get(data.slug) is not None:
            raise ConflictError("Já existe um grupo com este slug.")
        if await self._agents.get(data.slug) is not None:
            raise ConflictError("Já existe um agente com este slug (namespace compartilhado).")
        group = await self._groups.add(
            Group(slug=data.slug, display_name=data.display_name, created_by=actor.id)
        )
        await self._audit.record("group_created", actor=actor.email, detail={"slug": group.slug})
        return group

    async def delete(self, actor: User, slug: str) -> None:
        group = await self._get(slug)
        if group.created_by != actor.id and actor.role != "admin":
            raise PermissionDeniedError("Apenas o criador do grupo ou um admin podem removê-lo.")
        await self._groups.remove(group)
        await self._audit.record("group_deleted", actor=actor.email, detail={"slug": slug})

    async def list_with_members(self) -> list[tuple[Group, list[str]]]:
        groups = await self._groups.list_all()
        return [(group, await self._groups.members_of(group.slug)) for group in groups]

    # ---- membership: opt-in by the agent's owner ----

    async def add_member(self, actor: User, group_slug: str, agent_slug: str) -> None:
        await self._get(group_slug)
        await self._authorize_member_change(actor, agent_slug)
        if await self._groups.is_member(group_slug, agent_slug):
            return  # idempotent
        await self._groups.add_member(group_slug, agent_slug)
        await self._audit.record(
            "group_member_added",
            actor=actor.email,
            detail={"group": group_slug, "agent": agent_slug},
        )

    async def remove_member(self, actor: User, group_slug: str, agent_slug: str) -> None:
        await self._get(group_slug)
        await self._authorize_member_change(actor, agent_slug)
        await self._groups.remove_member(group_slug, agent_slug)
        await self._audit.record(
            "group_member_removed",
            actor=actor.email,
            detail={"group": group_slug, "agent": agent_slug},
        )

    # ---- resolution for broadcast ----

    async def resolve_recipients(self, group_ref: str, sender_slug: str) -> list[str]:
        """ "@all" → all agents; "@slug" → the group's members.
        The sender never receives their own message."""
        if not group_ref.startswith("@"):
            raise InvalidInputError("Referência de grupo deve começar com @.")
        name = group_ref[1:]
        if name == "all":
            slugs = [a.slug for a in await self._agents.list_all()]
        else:
            if await self._groups.get(name) is None:
                raise NotFoundError(f"Grupo {group_ref!r} não existe.")
            slugs = await self._groups.members_of(name)
        return [slug for slug in slugs if slug != sender_slug]

    # ---- internals ----

    async def _get(self, slug: str) -> Group:
        group = await self._groups.get(slug)
        if group is None:
            raise NotFoundError("Grupo não encontrado.")
        return group

    async def _authorize_member_change(self, actor: User, agent_slug: str) -> None:
        agent = await self._agents.get(agent_slug)
        if agent is None:
            raise NotFoundError(f"Agente {agent_slug!r} não existe.")
        if agent.user_id != actor.id and actor.role != "admin":
            raise PermissionDeniedError(
                "Apenas o dono do agente (ou admin) altera a participação dele em grupos."
            )
