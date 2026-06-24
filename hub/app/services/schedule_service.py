"""Scheduled agent tasks (Epic 08 · 8.3). Owns authorization and (kind, spec)
validation; the engine loop and routes call this layer.

Authorization: a user may only schedule an agent they own (admins, any). A
schedule is a privileged object — an agent will act unattended — so create /
enable / delete are audited, and granting write tools is the UI danger-zone.
`created_by` is the authenticated actor (anti-spoof); the engine never trusts a
schedule it didn't read from the DB.
"""

from app.models.schedule import AgentSchedule
from app.models.user import User, utcnow
from app.repositories.agent_repo import AgentRepository
from app.repositories.audit_repo import AuditRepository
from app.repositories.schedule_repo import ScheduleRepository
from app.schemas.schedule import ScheduleCreate, ScheduleUpdate
from app.services.errors import (
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
)
from app.services.scheduler import next_run, parse_interval, validate_spec

# Anti-flood floor for interval schedules (an agent waking too often). Overridable
# via settings; cron/once aren't interval-capped (cron's finest grain is 1/min).
DEFAULT_MIN_INTERVAL_SECS = 60


class ScheduleService:
    def __init__(
        self,
        schedules: ScheduleRepository,
        agents: AgentRepository,
        audit: AuditRepository,
        min_interval_secs: int = DEFAULT_MIN_INTERVAL_SECS,
    ) -> None:
        self._schedules = schedules
        self._agents = agents
        self._audit = audit
        self._min_interval = min_interval_secs

    # ---- commands ----

    async def create(self, user: User, agent_slug: str, data: ScheduleCreate) -> AgentSchedule:
        await self._owned_agent(user, agent_slug)
        self._validate(data.kind, data.spec)
        schedule = await self._schedules.add(
            AgentSchedule(
                owner_id=user.id,
                agent_slug=agent_slug,
                name=data.name.strip(),
                kind=data.kind,
                spec=data.spec.strip(),
                prompt=data.prompt,
                tools=data.tools,
                enabled=data.enabled,
                next_run_at=next_run(data.kind, data.spec.strip(), utcnow())
                if data.enabled
                else None,
                created_by=f"user:{user.id}",
            )
        )
        await self._audit.record(
            "schedule_created",
            actor=user.email,
            detail={
                "id": schedule.id,
                "agent": agent_slug,
                "kind": data.kind,
                "tools": data.tools,
            },
        )
        return schedule

    async def update(self, user: User, schedule_id: int, data: ScheduleUpdate) -> AgentSchedule:
        schedule = await self._owned_schedule(user, schedule_id)
        if data.name is not None:
            schedule.name = data.name.strip()
        if data.prompt is not None:
            schedule.prompt = data.prompt
        if data.tools is not None:
            schedule.tools = data.tools
        kind = data.kind or schedule.kind
        spec = (data.spec if data.spec is not None else schedule.spec).strip()
        timing_changed = data.kind is not None or data.spec is not None
        if timing_changed:
            self._validate(kind, spec)
            schedule.kind = kind
            schedule.spec = spec
        if data.enabled is not None:
            schedule.enabled = data.enabled
        # Recompute the next fire whenever timing or the enabled flag moved.
        if timing_changed or data.enabled is not None:
            schedule.next_run_at = next_run(kind, spec, utcnow()) if schedule.enabled else None
        schedule.updated_at = utcnow()
        await self._schedules.save(schedule)
        await self._audit.record(
            "schedule_updated",
            actor=user.email,
            detail={"id": schedule.id, "enabled": schedule.enabled},
        )
        return schedule

    async def delete(self, user: User, schedule_id: int) -> None:
        schedule = await self._owned_schedule(user, schedule_id)
        await self._schedules.delete(schedule)
        await self._audit.record("schedule_deleted", actor=user.email, detail={"id": schedule_id})

    async def run_now(self, user: User, schedule_id: int) -> AgentSchedule:
        """Owner-triggered immediate run: arm the schedule for now() so the engine
        fires it on the next tick (≤ tick interval later). Re-enables if disabled."""
        schedule = await self._owned_schedule(user, schedule_id)
        schedule.enabled = True
        schedule.next_run_at = utcnow()
        schedule.updated_at = utcnow()
        await self._schedules.save(schedule)
        await self._audit.record("schedule_run_now", actor=user.email, detail={"id": schedule_id})
        return schedule

    async def record_report(
        self, agent_slug: str, schedule_id: int, status: str, summary: str = ""
    ) -> None:
        """Record a daemon's run report (Epic 08 · 8.4), overwriting last_status.
        Anti-spoof: silently ignored unless the schedule belongs to the reporting
        (authenticated) agent — a daemon can't report for someone else's schedule.
        Best-effort: the run's real output already went to its destination."""
        schedule = await self._schedules.get(schedule_id)
        if schedule is None or schedule.agent_slug != agent_slug:
            return
        schedule.last_status = status
        schedule.updated_at = utcnow()
        await self._schedules.save(schedule)
        await self._audit.record(
            "scheduled_task_run",
            actor=agent_slug,
            detail={"id": schedule_id, "status": status},
        )

    # ---- queries ----

    async def list_for_agent(self, user: User, agent_slug: str) -> list[AgentSchedule]:
        await self._owned_agent(user, agent_slug)
        return await self._schedules.list_for_agent(agent_slug)

    async def get(self, user: User, schedule_id: int) -> AgentSchedule:
        return await self._owned_schedule(user, schedule_id)

    # ---- internals ----

    def _validate(self, kind: str, spec: str) -> None:
        try:
            validate_spec(kind, spec)
        except ValueError as exc:
            raise InvalidInputError(str(exc)) from exc
        if kind == "interval" and parse_interval(spec) < self._min_interval:
            raise InvalidInputError(f"O intervalo mínimo é de {self._min_interval} segundos.")

    async def _owned_agent(self, user: User, agent_slug: str):
        agent = await self._agents.get(agent_slug)
        if agent is None:
            raise NotFoundError(f"Agente {agent_slug!r} não existe.")
        if agent.user_id != user.id and user.role != "admin":
            raise PermissionDeniedError("Você só agenda tarefas para os seus próprios agentes.")
        return agent

    async def _owned_schedule(self, user: User, schedule_id: int) -> AgentSchedule:
        schedule = await self._schedules.get(schedule_id)
        # 404 (not 403) for another user's schedule: a 403 would confirm the id
        # exists, letting someone enumerate other users' schedules. Same
        # never-leak-existence convention as notifications and private boards.
        if schedule is None or (schedule.owner_id != user.id and user.role != "admin"):
            raise NotFoundError("Agendamento não encontrado.")
        return schedule
