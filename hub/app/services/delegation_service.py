"""Agent-to-agent task delegation (Epic 04 · 4.4).

An interactive agent hands a task to another agent (via the `amp_delegate` MCP
tool → daemon → WS); the hub turns it into a `task` message — so it flows through
the normal routing / allowlist / threading — plus a `delegations` row that tracks
the hand-off. When the delegate replies in-thread, MessageService marks the
delegation `completed` and notifies the delegator.

Security: `from_agent` is the socket's AUTHENTICATED slug (anti-spoof). Auto-
responding agents cannot delegate (`claude -p --strict-mcp-config` strips the
ampla MCP), so delegation is structurally human-in-the-loop — no agent↔agent
runaway. The delegate's allowlist still gates it (a block → `declined`). A
defensive cap bounds how many delegations one agent can have open at once.
"""

import logging
from collections.abc import Awaitable, Callable

from app.models.delegation import Delegation
from app.models.message import Message
from app.repositories.agent_repo import AgentRepository
from app.repositories.audit_repo import AuditRepository
from app.repositories.delegation_repo import DelegationRepository
from app.schemas.delegation import MAX_TASK_LEN
from app.services.errors import InvalidInputError, PermissionDeniedError

logger = logging.getLogger(__name__)

# Sends the task AS the delegator and dispatches it (persist + real-time push),
# returning the sent Message. Injected by the composition root so the service
# stays free of any transport import (like ApprovalSender). Raises
# PermissionDeniedError when the delegate's allowlist blocks the delegator.
DelegationSender = Callable[[str, str, str], Awaitable[Message]]

# Defensive blast-radius cap: an agent cannot have more than this many open
# delegations at once (bounds runaway even though auto-respond can't delegate).
DEFAULT_MAX_OPEN = 20


class DelegationService:
    def __init__(
        self,
        delegations: DelegationRepository,
        agents: AgentRepository,
        audit: AuditRepository,
        sender: DelegationSender | None = None,
        max_open: int = DEFAULT_MAX_OPEN,
    ) -> None:
        self._delegations = delegations
        self._agents = agents
        self._audit = audit
        self._sender = sender
        self._max_open = max_open

    @staticmethod
    def _build_body(delegator: str, task: str, context: str) -> str:
        """The task message body. The delegate's daemon wraps the whole thing as
        untrusted data in the prompt, so this is just a readable layout."""
        body = f"[Tarefa delegada por {delegator}]\n{task.strip()}"
        if context.strip():
            body += f"\n\nContexto:\n{context.strip()}"
        return body

    async def delegate(
        self, from_slug: str, to: str, task: str, context: str = ""
    ) -> Delegation | None:
        """Creates a delegation and sends the task to `to`. Returns the row
        (status `open`, or `declined` if the delegate's allowlist blocked it), or
        None if the delegator vanished (defensive)."""
        delegator = await self._agents.get(from_slug)
        if delegator is None:
            return None
        if from_slug == to:
            raise InvalidInputError("Não dá para delegar para o próprio agente.")
        if await self._delegations.count_open_from(from_slug) >= self._max_open:
            raise InvalidInputError("Muitas delegações abertas; conclua algumas antes.")
        if self._sender is None:  # pragma: no cover — always wired via deps
            raise InvalidInputError("Envio indisponível.")

        headline = task.strip()[:MAX_TASK_LEN]
        body = self._build_body(from_slug, task, context)
        try:
            message = await self._sender(from_slug, to, body)
        except PermissionDeniedError:
            # The delegate's allowlist won — record the attempt as declined so the
            # delegator can see it failed (already audited in message_service.send).
            declined = await self._delegations.add(
                Delegation(from_agent=from_slug, to_agent=to, task=headline, status="declined")
            )
            await self._audit.record(
                "delegation_declined", actor=from_slug, detail={"to": to, "id": declined.id}
            )
            return declined

        delegation = await self._delegations.add(
            Delegation(
                from_agent=from_slug,
                to_agent=to,
                task=headline,
                root_message_id=message.id,
                status="open",
            )
        )
        await self._audit.record(
            "delegation_created",
            actor=from_slug,
            detail={"to": to, "id": delegation.id, "message_id": message.id},
        )
        return delegation

    async def list_for_agent(self, agent_slug: str, *, limit: int = 50) -> list[Delegation]:
        return await self._delegations.list_for_agent(agent_slug, limit=min(max(limit, 1), 200))
