"""The scheduler engine (Epic 08 · 8.1/8.2/8.4): one in-process async loop that
fires due agent schedules over the WS and runs the maintenance sweeps on an
interval (not just at startup).

Design (per the spec): hand-rolled tick loop, no APScheduler. A due schedule is
*claimed* by advancing its next_run_at in the same transaction it is read, so a
slow run can't double-fire on the next tick. The next fire is computed from NOW,
which collapses missed runs (hub was down) into a single catch-up. Single hub
process is assumed (SQLite's one-writer claim suffices); a multi-process deploy
would need a row lock — out of scope.

Safety: a scheduled run is suppressed by the global kill switch and a per-agent
pause, exactly like auto-respond; an offline agent's run is skipped (not queued)
and re-anchored to the next slot. Every fire/skip is audited.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from app.api.deps import build_approval_service, build_notification_service
from app.models.user import utcnow
from app.repositories.agent_repo import AgentRepository
from app.repositories.audit_repo import AuditRepository
from app.repositories.hub_state_repo import HubStateRepository
from app.repositories.schedule_repo import ScheduleRepository
from app.schemas.ws import ScheduledTaskFrame
from app.services.scheduler import next_run

logger = logging.getLogger(__name__)


class SchedulerEngine:
    def __init__(self, session_factory, manager, settings) -> None:
        self._sf = session_factory
        self._manager = manager
        self._settings = settings
        self._last_sweep: datetime | None = None

    async def run_forever(self) -> None:
        """The lifespan task: tick, sleep, repeat. A tick never raises out of the
        loop (a failure is logged and the loop survives)."""
        tick = max(self._settings.scheduler_tick_secs, 1.0)
        # The lifespan already ran the boot sweep; defer the engine's first
        # recurring sweep by one interval so they don't double up at startup.
        self._last_sweep = utcnow()
        logger.info("scheduler engine started (tick=%ss)", tick)
        while True:
            try:
                await self.tick(utcnow())
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("scheduler tick failed", exc_info=True)
            await asyncio.sleep(tick)

    async def tick(self, now: datetime) -> None:
        await self._run_due_schedules(now)
        await self._maybe_sweep(now)

    # ---- agent schedules ----

    async def _run_due_schedules(self, now: datetime) -> None:
        async with self._sf() as session:
            schedules = await ScheduleRepository(session).due(now)
            if not schedules:
                return
            kill_enabled = (await HubStateRepository(session).get()).auto_responder_enabled
            agents = AgentRepository(session)
            repo = ScheduleRepository(session)
            audit = AuditRepository(session)
            for s in schedules:
                # Claim: re-anchor next_run from NOW (collapses missed runs) BEFORE
                # firing, so a slow/again-due run can't double-fire next tick.
                s.next_run_at = next_run(s.kind, s.spec, now)
                s.last_run_at = now
                s.updated_at = now
                # A throwing job is recorded `failed` and never kills the loop or
                # aborts the other due schedules in this tick (spec 8.1).
                try:
                    agent = await agents.get(s.agent_slug)
                    s.last_status = await self._fire(s, agent, kill_enabled)
                except Exception:
                    logger.warning("scheduled task %s failed to fire", s.id, exc_info=True)
                    s.last_status = "failed"
                await repo.save(s)
                await audit.record(
                    "scheduled_task_fired",
                    actor="scheduler",
                    detail={"id": s.id, "agent": s.agent_slug, "status": s.last_status},
                )

    async def _fire(self, schedule, agent, kill_enabled: bool) -> str:
        """Send the task to the agent if everything's clear; return the status that
        becomes last_status. The daemon's report later overwrites a sent run with
        its terminal ok/failed/blocked."""
        if not kill_enabled:
            return "skipped_killswitch"
        if agent is None:
            return "skipped_offline"
        if getattr(agent, "auto_paused", False):
            return "skipped_paused"
        if not self._manager.is_online(schedule.agent_slug):
            return "skipped_offline"
        frame = ScheduledTaskFrame(
            schedule_id=schedule.id,
            name=schedule.name,
            prompt=schedule.prompt,
            tools=schedule.tools,
        ).model_dump(mode="json")
        sent = await self._manager.send_to_agent(schedule.agent_slug, frame)
        return "running" if sent else "skipped_offline"

    # ---- maintenance sweeps (Epic 08 · 8.2) ----

    async def _maybe_sweep(self, now: datetime) -> None:
        """Run retention/expiry on the configured cadence (the startup sweep is the
        first one). Best-effort: a failure never kills the loop."""
        interval = timedelta(hours=max(self._settings.retention_sweep_interval_hours, 1))
        if self._last_sweep is not None and now - self._last_sweep < interval:
            return
        self._last_sweep = now
        async with self._sf() as session:
            audit = AuditRepository(session)
            try:
                pruned = await build_notification_service(session, self._settings).prune_done(
                    self._settings.notification_done_ttl_days
                )
                if pruned:
                    logger.info("retention: pruned %s done notifications", pruned)
                    # The prune deletes rows — an auditable mutation (spec 8.2).
                    await audit.record(
                        "notifications_pruned", actor="scheduler", detail={"count": pruned}
                    )
            except Exception:
                logger.warning("scheduled notification prune failed", exc_info=True)
            try:
                # expire_pending already records its own `approvals_expired` audit.
                expired = await build_approval_service(session, self._settings).expire_pending(
                    self._settings.approval_ttl_hours
                )
                if expired:
                    logger.info("expired %s stale pending approvals", expired)
            except Exception:
                logger.warning("scheduled approval expiry failed", exc_info=True)
