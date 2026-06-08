"""Agents, settings and keys. The owner manages their own; an admin manages all."""

import re

from app.core import security
from app.models.agent import Agent, AgentKey
from app.models.user import User, utcnow
from app.repositories.agent_repo import AgentRepository
from app.repositories.audit_repo import AuditRepository
from app.repositories.group_repo import GroupRepository
from app.schemas.agent import (
    RESERVED_SLUGS,
    SLUG_PATTERN,
    AgentCreate,
    AgentSettings,
    AgentSettingsUpdate,
)
from app.services.errors import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
)

_SLUG_RE = re.compile(SLUG_PATTERN)


class AgentService:
    def __init__(
        self,
        agents: AgentRepository,
        audit: AuditRepository,
        groups: GroupRepository | None = None,
    ) -> None:
        self._agents = agents
        self._audit = audit
        self._groups = groups

    async def create(self, owner: User, data: AgentCreate) -> Agent:
        if not _SLUG_RE.fullmatch(data.slug):
            raise InvalidInputError("Slug inválido (use kebab-case: backend-julio).")
        if data.slug in RESERVED_SLUGS:
            raise InvalidInputError(f"{data.slug!r} é reservado.")
        if await self._agents.get(data.slug) is not None:
            raise ConflictError("Já existe um agente com este slug.")
        if self._groups is not None and await self._groups.get(data.slug) is not None:
            raise ConflictError("Já existe um grupo com este slug (namespace compartilhado).")
        agent = await self._agents.add(
            Agent(slug=data.slug, user_id=owner.id, display_name=data.display_name)
        )
        await self._audit.record("agent_created", actor=owner.email, detail={"slug": agent.slug})
        return agent

    async def list_for_user(self, user: User) -> list[Agent]:
        return await self._agents.list_by_user(user.id)

    async def list_all(self) -> list[Agent]:
        return await self._agents.list_all()

    async def get_owned(self, actor: User, slug: str) -> Agent:
        """Loads the agent, ensuring the actor is the owner or an admin."""
        agent = await self._agents.get(slug)
        if agent is None:
            raise NotFoundError("Agente não encontrado.")
        if agent.user_id != actor.id and actor.role != "admin":
            raise PermissionDeniedError("Você não gerencia este agente.")
        return agent

    # ---- settings ----

    async def update_settings(self, actor: User, slug: str, patch: AgentSettingsUpdate) -> Agent:
        agent = await self.get_owned(actor, slug)
        changed: dict = {}
        if patch.mode is not None:
            agent.mode = patch.mode
            changed["mode"] = patch.mode
        if patch.clear_allowed_senders:
            agent.allowed_senders = None
            changed["allowed_senders"] = None
        elif patch.allowed_senders is not None:
            for sender in patch.allowed_senders:
                if not _SLUG_RE.fullmatch(sender):
                    raise InvalidInputError(f"Slug inválido na allowlist: {sender!r}")
            agent.allowed_senders = patch.allowed_senders
            changed["allowed_senders"] = patch.allowed_senders
        if patch.max_auto_per_hour is not None:
            agent.max_auto_per_hour = patch.max_auto_per_hour
            changed["max_auto_per_hour"] = patch.max_auto_per_hour
        if patch.auto_timeout_secs is not None:
            agent.auto_timeout_secs = patch.auto_timeout_secs
            changed["auto_timeout_secs"] = patch.auto_timeout_secs
        if patch.instructions is not None:
            agent.instructions = patch.instructions
            changed["instructions"] = True  # content does not go to the audit
        if patch.allow_write is not None:
            agent.allow_write = patch.allow_write
            changed["allow_write"] = patch.allow_write
        if patch.block_hidden_files is not None:
            agent.block_hidden_files = patch.block_hidden_files
            changed["block_hidden_files"] = patch.block_hidden_files
        if patch.block_sensitive_paths is not None:
            agent.block_sensitive_paths = patch.block_sensitive_paths
            changed["block_sensitive_paths"] = patch.block_sensitive_paths
        if patch.confine_to_dir is not None:
            agent.confine_to_dir = patch.confine_to_dir
            changed["confine_to_dir"] = patch.confine_to_dir
        if patch.denied_paths is not None:
            agent.denied_paths = patch.denied_paths
            changed["denied_paths"] = patch.denied_paths
        if patch.trusted_senders is not None:
            for sender in patch.trusted_senders:
                if not _SLUG_RE.fullmatch(sender):
                    raise InvalidInputError(f"Slug inválido em trusted_senders: {sender!r}")
            agent.trusted_senders = patch.trusted_senders
            changed["trusted_senders"] = patch.trusted_senders
        await self._agents.save(agent)
        await self._audit.record(
            "settings_changed", actor=actor.email, detail={"slug": slug, "fields": list(changed)}
        )
        return agent

    def settings_of(self, agent: Agent) -> AgentSettings:
        return AgentSettings.model_validate(agent)

    # ---- keys ----

    async def create_key(self, actor: User, slug: str, label: str = "") -> tuple[AgentKey, str]:
        agent = await self.get_owned(actor, slug)
        plaintext = security.generate_agent_key()
        key = await self._agents.add_key(
            AgentKey(
                agent_slug=agent.slug,
                key_hash=security.hash_agent_key(plaintext),
                label=label,
            )
        )
        await self._audit.record(
            "key_created", actor=actor.email, detail={"slug": slug, "key_id": key.id}
        )
        return key, plaintext

    async def list_keys(self, actor: User, slug: str) -> list[AgentKey]:
        await self.get_owned(actor, slug)
        return await self._agents.list_keys(slug)

    async def revoke_key(self, actor: User, slug: str, key_id: int) -> AgentKey:
        await self.get_owned(actor, slug)
        key = await self._agents.get_key(key_id)
        if key is None or key.agent_slug != slug:
            raise NotFoundError("Chave não encontrada.")
        if key.revoked_at is None:
            key.revoked_at = utcnow()
            await self._agents.save_key(key)
            await self._audit.record(
                "key_revoked", actor=actor.email, detail={"slug": slug, "key_id": key_id}
            )
        return key

    # ---- daemon authentication (hello frame) ----

    async def authenticate_key(self, agent_id: str, key: str) -> Agent | None:
        """Resolves the key to its agent. None ⇒ failure (audited here)."""
        found = await self._agents.get_key_by_hash(security.hash_agent_key(key))
        if found is None or found.revoked_at is not None or found.agent_slug != agent_id:
            await self._audit.record("ws_auth_fail", actor=agent_id or "?")
            return None
        return await self._agents.get(found.agent_slug)
