"""Instance observability. Authorization (admin-only) is enforced at the route
via require_admin; this service assumes a vetted actor and only reads. No audit
record — reading metrics is not a mutation."""

from datetime import timedelta

from app.models.user import utcnow
from app.repositories.audit_repo import AuditRepository
from app.repositories.autorespond_repo import AutorespondRunRepository
from app.repositories.message_repo import MessageRepository
from app.schemas.metrics import MetricsOut


class MetricsService:
    def __init__(
        self,
        runs: AutorespondRunRepository,
        audit: AuditRepository,
        messages: MessageRepository,
    ) -> None:
        self._runs = runs
        self._audit = audit
        self._messages = messages

    async def snapshot(self, days: int) -> MetricsOut:
        """Aggregate the last `days` of activity into one panel-ready snapshot."""
        now = utcnow()
        since = now - timedelta(days=days)
        agg = await self._runs.aggregate(since)
        return MetricsOut(
            window_days=days,
            generated_at=now,
            messages_total=await self._messages.count_since(since),
            autorespond=agg,
            autorespond_daily=await self._runs.daily_series(since),
            audit_events=await self._audit.event_counts(since),
        )
