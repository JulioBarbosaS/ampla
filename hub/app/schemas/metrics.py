"""Instance observability snapshot (GET /api/admin/metrics). Admin-only,
read-only aggregation over autorespond_runs + audit_log + messages."""

from datetime import datetime

from pydantic import BaseModel


class AutorespondMetrics(BaseModel):
    """Windowed roll-up of auto-respond activity (cost + security posture)."""

    total_runs: int
    by_result: dict[str, int]  # replied|blocked|failed|skipped → count
    timed_out: int
    total_cost_usd: float
    total_output_tokens: int
    total_input_tokens: int
    avg_duration_ms: int


class DailyPoint(BaseModel):
    date: str  # YYYY-MM-DD (UTC)
    runs: int
    cost_usd: float


class EventCount(BaseModel):
    event: str
    count: int


class MetricsOut(BaseModel):
    window_days: int
    generated_at: datetime
    messages_total: int
    autorespond: AutorespondMetrics
    autorespond_daily: list[DailyPoint]
    audit_events: list[EventCount]
