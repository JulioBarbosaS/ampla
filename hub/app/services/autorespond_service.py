"""Auto-respond transcript (Epic 03 · 3.1). Records what each headless run did.

Read authorization (owner/admin for a single agent, admin for the instance-wide
list) is enforced at the route. record_run is called from the WS layer with the
socket's AUTHENTICATED slug, so the stored agent_slug can never be spoofed."""

from app.models.autorespond_run import AutorespondRun
from app.repositories.autorespond_repo import AutorespondRunRepository
from app.schemas.ws import AutorespondRecord

# Cap on rows returned by the read endpoints (defensive — bounds the response).
MAX_LIMIT = 200


class AutorespondService:
    def __init__(self, runs: AutorespondRunRepository) -> None:
        self._runs = runs

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
        return await self._runs.add(run)

    async def list_for_agent(self, agent_slug: str, limit: int = 50) -> list[AutorespondRun]:
        return await self._runs.list_for_agent(agent_slug, min(max(limit, 1), MAX_LIMIT))

    async def list_all(self, limit: int = 50) -> list[AutorespondRun]:
        return await self._runs.list_all(min(max(limit, 1), MAX_LIMIT))
