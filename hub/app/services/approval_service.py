"""Human-in-the-loop auto-reply approvals (Epic 03 · 3.3).

The daemon drafts a reply and requests approval instead of sending; the hub
persists it and notifies the agent's owner. The owner decides in the panel and
the hub sends server-side (decision flow lands in the next slice).

Authorization: only the agent's owner (or an admin) can see/decide its
approvals.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta

from app.models.agent import Agent
from app.models.approval import Approval
from app.models.message import Message
from app.models.user import User, utcnow
from app.repositories.agent_repo import AgentRepository
from app.repositories.approval_repo import ApprovalRepository
from app.repositories.audit_repo import AuditRepository
from app.services.errors import InvalidInputError, NotFoundError, PermissionDeniedError
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

MAX_LIMIT = 100

# Sends the approved reply AS the agent and delivers it (persist + real-time
# push). Injected by the composition root so the service stays free of any
# transport import (dependency inversion, like NotificationService.publisher).
# Signature: (from_slug, to_slug, body, in_reply_to) -> the sent Message.
ApprovalSender = Callable[[str, str, str, int | None], Awaitable[Message]]


class ApprovalService:
    def __init__(
        self,
        approvals: ApprovalRepository,
        agents: AgentRepository,
        audit: AuditRepository,
        notifications: NotificationService | None = None,
        sender: ApprovalSender | None = None,
    ) -> None:
        self._approvals = approvals
        self._agents = agents
        self._audit = audit
        self._notifications = notifications
        self._sender = sender

    async def create_request(
        self,
        agent_slug: str,
        to: str,
        draft_body: str,
        trigger_message_id: int | None = None,
    ) -> Approval | None:
        """Persists a pending approval for the authenticated agent and notifies
        its owner. Returns None if the agent vanished (defensive)."""
        agent = await self._agents.get(agent_slug)
        if agent is None:
            return None
        approval = await self._approvals.add(
            Approval(
                agent_slug=agent_slug,
                to_agent=to,
                draft_body=draft_body,
                trigger_message_id=trigger_message_id,
            )
        )
        # Notify the owner (best-effort: the approval row is the source of truth,
        # so a notification failure must never drop it). approval_requested is an
        # always-deliver reason → it reaches the owner regardless of notify_level.
        if self._notifications is not None:
            try:
                await self._notifications.notify(
                    agent.user_id,
                    subject_type="approval",
                    subject_key=f"approval:{approval.id}",
                    reason="approval_requested",
                    title=f"{agent_slug} quer responder a {to} — aguardando aprovação",
                    link=f"/?perspective={agent_slug}&partner={to}",
                    actor=agent_slug,
                    agent_slug=agent_slug,
                )
            except Exception:
                logger.warning(
                    "approval notification failed for approval %s", approval.id, exc_info=True
                )
        return approval

    async def _owned(self, actor: User, agent_slug: str) -> Agent:
        agent = await self._agents.get(agent_slug)
        if agent is None:
            raise NotFoundError("Agente não encontrado.")
        if agent.user_id != actor.id and actor.role != "admin":
            raise PermissionDeniedError("Você não gerencia este agente.")
        return agent

    async def list_for_agent(
        self, actor: User, agent_slug: str, *, status: str | None = None, limit: int = 50
    ) -> list[Approval]:
        await self._owned(actor, agent_slug)
        return await self._approvals.list_for_agent(
            agent_slug, status=status, limit=min(max(limit, 1), MAX_LIMIT)
        )

    async def decide(
        self, actor: User, approval_id: int, decision: str, body: str | None = None
    ) -> tuple[Approval, Message | None]:
        """Owner approves/edits/rejects a pending approval. On approve/edit the
        reply is sent AS the agent (server-side, via the injected sender) so it
        works even if the daemon disconnected. Returns (approval, sent message)."""
        approval = await self._approvals.get(approval_id)
        if approval is None:
            raise NotFoundError("Aprovação não encontrada.")
        await self._owned(actor, approval.agent_slug)  # owner/admin only
        if approval.status != "pending":
            raise InvalidInputError("Esta aprovação já foi decidida.")

        message: Message | None = None
        if decision == "approve":
            if self._sender is None:  # pragma: no cover — always wired via deps
                raise InvalidInputError("Envio indisponível.")
            final_body = body or approval.draft_body
            message = await self._sender(
                approval.agent_slug, approval.to_agent, final_body, approval.trigger_message_id
            )
            approval.status = "edited" if body else "approved"
        else:  # reject — nothing is sent
            approval.status = "rejected"
        approval.decided_by = actor.id
        approval.decided_at = utcnow()
        await self._approvals.save(approval)
        await self._audit.record(
            "approval_decided",
            actor=actor.email,
            detail={"id": approval_id, "decision": decision, "agent": approval.agent_slug},
        )
        return approval, message

    async def expire_pending(self, ttl_hours: int) -> int:
        """Auto-reject pending approvals older than ttl_hours so nothing hangs
        forever (run best-effort at startup). ttl_hours <= 0 disables it."""
        if ttl_hours <= 0:
            return 0
        cutoff = utcnow() - timedelta(hours=ttl_hours)
        stale = await self._approvals.list_pending_before(cutoff)
        for approval in stale:
            approval.status = "rejected"
            approval.decided_at = utcnow()
            await self._approvals.save(approval)
        if stale:
            await self._audit.record("approvals_expired", detail={"count": len(stale)})
        return len(stale)
