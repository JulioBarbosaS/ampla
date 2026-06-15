"""Auto-respond transcript (Epic 03 · 3.1). Records what each headless run did.

Read authorization (owner/admin for a single agent, admin for the instance-wide
list) is enforced at the route. record_run is called from the WS layer with the
socket's AUTHENTICATED slug, so the stored agent_slug can never be spoofed.

It also drives escalation (Epic 04 · 4.3): when a run ends in an outcome the
owner opted into (`escalate_on`), or the model emits the explicit `__ESCALATE__`
sentinel, the run's trigger message is routed to the owner's Inbox instead of
being silently dropped."""

import logging

from app.models.autorespond_run import AutorespondRun
from app.repositories.agent_repo import AgentRepository
from app.repositories.autorespond_repo import AutorespondRunRepository
from app.schemas.ws import AutorespondRecord
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

# Cap on rows returned by the read endpoints (defensive — bounds the response).
MAX_LIMIT = 200

# The daemon's explicit "I can't answer this" signal (the `__ESCALATE__`
# sentinel, reported as a skipped run). It ALWAYS escalates, regardless of the
# agent's escalate_on — it is a deliberate model decision, not a filtered outcome.
ESCALATE_SENTINEL = "escalate"

# Skipped reasons that map to a configurable escalation outcome (Epic 04 · 4.3).
_SKIPPED_OUTCOMES = frozenset({"rate_limited", "budget_exceeded", "outside_hours"})

# Owner-facing escalation titles per outcome (pt-BR — product copy).
_ESCALATION_TITLES = {
    "failed": "{agent} não conseguiu responder a {sender} (falha no auto-respond)",
    "blocked": "Resposta de {agent} a {sender} bloqueada pelo filtro de segurança",
    "rate_limited": "{agent} atingiu o limite de respostas — mensagem de {sender} aguardando",
    "budget_exceeded": "{agent} estourou o orçamento diário — mensagem de {sender} aguardando",
    "outside_hours": "{agent} está fora do horário — mensagem de {sender} aguardando",
    ESCALATE_SENTINEL: "{agent} encaminhou uma mensagem de {sender} para você decidir",
}


def escalation_outcome(record: AutorespondRecord) -> tuple[str, bool] | None:
    """Maps a reported run to its escalation outcome, or None when it should
    never escalate. Returns (outcome, forced): `forced` outcomes (the
    `__ESCALATE__` sentinel) escalate regardless of the agent's escalate_on."""
    if record.result == "failed":
        return ("failed", False)
    if record.result == "blocked":
        return ("blocked", False)
    if record.result == "skipped":
        if record.reason == ESCALATE_SENTINEL:
            return (ESCALATE_SENTINEL, True)
        if record.reason in _SKIPPED_OUTCOMES:
            return (record.reason, False)
    return None  # replied, or a benign skip (mode_inbox) — nothing to escalate


class AutorespondService:
    def __init__(
        self,
        runs: AutorespondRunRepository,
        agents: AgentRepository | None = None,
        notifications: NotificationService | None = None,
    ) -> None:
        self._runs = runs
        self._agents = agents
        self._notifications = notifications

    async def record_run(self, agent_slug: str, record: AutorespondRecord) -> AutorespondRun:
        run = AutorespondRun(
            agent_slug=agent_slug,  # authenticated socket slug — not from the record
            trigger_message_id=record.trigger_message_id,
            from_sender=record.from_sender,
            result=record.result,
            reason=record.reason,
            reply_preview=record.reply_preview,
            tools_allowed=record.tools_allowed,
            tools_disallowed=record.tools_disallowed,
            guardrails=record.guardrails,
            duration_ms=record.duration_ms,
            timed_out=record.timed_out,
            input_tokens=record.input_tokens,
            output_tokens=record.output_tokens,
            cost_usd=record.cost_usd,
        )
        saved = await self._runs.add(run)
        await self._maybe_escalate(agent_slug, record)
        return saved

    async def _maybe_escalate(self, agent_slug: str, record: AutorespondRecord) -> None:
        """Routes a non-answer to the owner's Inbox (reason `escalation`). The run
        row is the source of truth, so escalation is best-effort: a failure here
        must never propagate and drop the recorded run."""
        if self._agents is None or self._notifications is None:
            return
        outcome = escalation_outcome(record)
        if outcome is None:
            return
        token, forced = outcome
        agent = await self._agents.get(agent_slug)
        if agent is None:
            return
        if not forced and token not in (agent.escalate_on or []):
            return  # owner did not opt into this outcome
        sender = record.from_sender
        link = f"/?perspective={agent_slug}&partner={sender}"
        if record.trigger_message_id is not None:
            link += f"&msg={record.trigger_message_id}"
        try:
            await self._notifications.notify(
                agent.user_id,
                subject_type="escalation",
                # Same key as the conversation's inbox thread, so the escalation
                # collapses onto it (and `escalation` outranks `direct_message`).
                subject_key=f"dm:{agent_slug}:{sender}",
                reason="escalation",
                title=_ESCALATION_TITLES[token].format(agent=agent_slug, sender=sender),
                link=link,
                actor=agent_slug,
                agent_slug=agent_slug,
            )
        except Exception:
            logger.warning(
                "escalation notification failed for %s (outcome=%s)",
                agent_slug,
                token,
                exc_info=True,
            )

    async def list_for_agent(self, agent_slug: str, limit: int = 50) -> list[AutorespondRun]:
        return await self._runs.list_for_agent(agent_slug, min(max(limit, 1), MAX_LIMIT))

    async def list_all(self, limit: int = 50) -> list[AutorespondRun]:
        return await self._runs.list_all(min(max(limit, 1), MAX_LIMIT))
