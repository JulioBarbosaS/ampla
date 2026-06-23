# Epic 08 — Scheduled Agent Tasks

> From the project-suggestions list · **item #9** (scheduled agent tasks), and it
> absorbs **item #5** (a real scheduler) — the two share the same engine.

An agent that **wakes on a schedule and acts** — a cron/interval job that drives
an interactive-style agent run (post a standup to the board, sweep open
delegations, run a health check and message the owner). This is the first place
an Ampla agent does work **without an incoming message to react to**, so it needs
the same threat discipline as auto-respond, plus a genuine scheduler the hub
doesn't have yet.

Today the hub runs its maintenance sweeps (notification retention, approval
expiration) **once, at startup** — `main.py` even comments *"A live scheduler is
future work."* This epic builds that scheduler and folds the sweeps into it, then
puts scheduled **agent** tasks on top.

Files in play: `hub/app/main.py` (lifespan), a new
`hub/app/services/scheduler_service.py` + `schedule_service.py`,
`hub/app/models/schedule.py`, `hub/app/repositories/schedule_repo.py`,
`hub/app/api/routes/schedules.py`, `hub/app/schemas/{schedule,ws}.py`,
`hub/app/core/config.py`, `bridge/src/shared/protocol.ts`,
`bridge/src/daemon/{index,ws-client}.ts`, `bridge/src/daemon/auto-responder.ts`
(reuses the runner), `web/src/features/agents/*`, `web/src/lib/{api,ws}/*`.

> Builds on: the WS daemon connection + presence (`ConnectionManager.is_online` /
> `send_to_agent`), the `claude -p` runner and guardrail presets (Epic 04 ·
> auto-respond), the kill switch + per-agent pause (Epic 03), the `audit_log`, the
> Inbox (Epic 02), and the `pending`-on-reconnect delivery pattern in `hello_ack`.

## Current state (grounding)

- **No scheduler.** The only periodic `asyncio` loops are the WS heartbeat
  (`ws.py:168`) and on-demand rank work — neither is a job scheduler. No
  APScheduler, cron, or persisted jobs anywhere.
- **Startup-only maintenance** in `main.py` lifespan (`main.py:55`):
  `NotificationService.prune_done(ttl_days)` (`notification_service.py:240`,
  `AMP_NOTIFICATION_DONE_TTL_DAYS=90`) and `ApprovalService.expire_pending(ttl_hours)`
  (`approval_service.py:142`, `AMP_APPROVAL_TTL_HOURS=48`). Best-effort; a failure
  never blocks boot. **These never run again until the next restart.**
- **The act path.** An agent runs `claude -p` only in reaction to an inbound
  `message`: `daemon/index.ts` `hub.on("message")` → `maybeAutoRespond` →
  `responder.handle` → `defaultClaudeRunner` → `runProcess(spawn("claude", claudeArgs(...)))`
  (`auto-responder.ts:296`/`343`), gated by the kill switch + per-agent pause +
  guardrails (`buildGuardrails`, `auto-responder.ts:88`). There is **no** hub→daemon
  frame today that says "run this task now."
- **Presence + delivery.** `ConnectionManager.is_online(slug)` /
  `online_slugs()` / `send_to_agent(slug, payload)` (`connection_manager.py`);
  offline agents pick up queued state via `pending` in `hello_ack` on reconnect.
- **Identity.** Daemons authenticate with an agent key (`authenticate_key`,
  `agent_service.py:183`); the authenticated socket slug is the anti-spoof actor.
- **Audit.** `AuditRepository.record(event, actor="", detail=None)`
  (`audit_repo.py:11`).
- **Config.** Pydantic `Settings`, `env_prefix="AMP_"` (`core/config.py`).

---

## 8.1 The scheduler engine (real periodic loop) · `◻ planned` · risk: med

**Goal.** One in-process async scheduler that wakes on a tick, runs due jobs,
computes the next run, and survives restarts — replacing "run once at startup."

**Design — hand-rolled tick loop, not a new heavy dependency.** At the local-hub
scale, a single `asyncio` task started in the lifespan (the same pattern as the
heartbeat) is enough; **decision: do not add APScheduler in v1** (it brings a job
store, executors and timezone machinery we'd mostly bypass on SQLite). The loop:

1. Started in `main.py` lifespan when `AMP_SCHEDULER_ENABLED=true` (default on for
   the bundled image, off in tests unless asked); cancelled cleanly on shutdown.
2. Every `AMP_SCHEDULER_TICK_SECS` (e.g. 30s) it reads **due** jobs
   (`next_run_at <= now`, `enabled`) in one serialized transaction, claims each by
   advancing `next_run_at` *before* firing (so a slow run can't double-fire on the
   next tick), fires it, and records `last_run_at`/`last_status`.
3. **Catch-up policy:** a job whose `next_run_at` is far in the past (hub was down)
   runs **once** and re-anchors to the next future slot — never N times for N missed
   intervals. Recorded as `catch_up:true` in the audit.
4. All times UTC; cron/interval math is a pure, unit-tested helper
   (`next_run(spec, after)`), like `compute_rank` in Epic 06.

**Single-instance assumption.** v1 assumes one hub process (the self-hosted
default). The "claim by advancing `next_run_at` in a serialized txn" guard is
already multi-worker-safe for SQLite's single writer; a note in the spec flags that
a multi-process deploy (Postgres, suggestion #6) would need a row lock / advisory
lock — out of scope here but called out.

**Security.** The engine is internal; it takes no external input. Each fire audits.

**Tests.** Unit (pure): `next_run` for cron + interval + once; DST/timezone fixed
to UTC; catch-up collapses missed runs to one. Engine: a due job fires once per due
window; advancing `next_run_at` before firing prevents double-fire; a job that
throws is recorded failed and doesn't kill the loop; disabling mid-flight stops
future fires. (Time is injected — no wall-clock in tests.)

**Effort.** ~2 days.

---

## 8.2 Fold the maintenance sweeps into the scheduler · `◻ planned` · risk: low

**Goal.** Make retention/expiration *recurring*, not boot-only — delivering
suggestion #5 as a built-in job set.

**Design.** Register two **internal** jobs (not user-editable, `kind=system`):
`prune_done` and `expire_pending`, on an interval
(`AMP_RETENTION_SWEEP_INTERVAL_HOURS`, e.g. 24h), calling the existing service
methods unchanged. Keep the **startup sweep** as an immediate catch-up on boot
(so a long-stopped hub cleans up at once), then hand off to the recurring job.

**Security.** Same as today (internal maintenance); audited per run with counts
(`notifications_pruned`, `approvals_expired`) — the audit already exists for
expiry; add it for the prune.

**Tests.** The two system jobs are registered when the scheduler starts; each
calls its service method on schedule and audits the count; they're hidden from the
user-facing schedule API (8.3) and can't be deleted.

**Effort.** ~0.5 day.

---

## 8.3 Schedule data model + CRUD · `◻ planned` · risk: med

**Goal.** Owners define **agent** schedules; the hub stores and manages them.

**Model.** `agent_schedules` (one Alembic revision; new table):
| column | type | notes |
|---|---|---|
| `id` | int PK | |
| `owner_id` | int FK→users.id | the human who owns the schedule + the agent |
| `agent_slug` | str(60) | the agent that wakes (must belong to `owner_id`) |
| `name` | str(120) | human label |
| `kind` | str(8) | `cron` \| `interval` \| `once` |
| `spec` | str(120) | cron expr, interval secs, or an ISO instant (per `kind`) |
| `prompt` | text | the **task** handed to the agent (owner-authored ⇒ trusted) |
| `tools` | str | guardrail preset reused from auto-respond (read-only by default) |
| `enabled` | bool | toggle without deleting |
| `next_run_at` / `last_run_at` | UTCDateTime \| null | engine-managed |
| `last_status` | str(12) \| null | `ok` \| `skipped_offline` \| `failed` \| `blocked` |
| `created_by` | str(60) | authenticated actor |
| `created_at` / `updated_at` | UTCDateTime | |

**Endpoints (REST).** `GET/POST /api/agents/{slug}/schedules`,
`GET/PATCH/DELETE /api/schedules/{id}`, `POST /api/schedules/{id}/run` (run-now,
owner-triggered). All via a new `ScheduleService`; routes never touch repos.
Validation: cron/interval parse-checks (422 on a bad spec), a **minimum interval**
(`AMP_SCHEDULE_MIN_INTERVAL_SECS`, anti-flood), prompt size bound.

**Security.** **Owner/admin-only**, and only for an agent the user owns (a user
can't schedule someone else's agent). Creating or enabling a schedule is a
**privileged action** (an agent will act unattended) → audited (`schedule_created`
/ `schedule_enabled` / `schedule_deleted`) and, in the UI (8.5), behind the
**danger-zone confirm** when the preset grants write/tool access — same treatment
as `trusted_senders` and kanban grants. The `prompt` is owner-authored, so it's the
**one place an agent is deliberately driven by trusted input** (contrast: inbound
messages are untrusted, §8.4 Security).

**Tests.** Service unit: CRUD + ownership (can't schedule another user's agent);
bad cron/interval → 422; min-interval enforced; toggling sets/clears `next_run_at`.
Integration: REST authz (cross-user 403/404), golden `openapi.json`. Property: any
valid cron/interval yields a strictly-future `next_run_at`.

**Effort.** ~1.5 days.

---

## 8.4 Firing a task to the agent (the act) · `◻ planned` · risk: high

**Goal.** When a job is due and the agent is online, make its daemon run the task;
report the result back.

**Protocol (mirror `ws.py` ↔ `protocol.ts`, regenerate `ws_frames.json`).**
- hub→daemon **`scheduled_task`** `{schedule_id, name, prompt, tools}` — sent via
  `send_to_agent(slug, ...)` when `is_online(slug)`. The daemon handles it by
  running the **existing** `claude -p` path (`defaultClaudeRunner` + `buildGuardrails`),
  *not* a new runner — reuse, don't fork.
- daemon→hub **`scheduled_task_report`** `{schedule_id, status, summary?, usage?}` —
  status `ok|failed|blocked`; mirrors `autorespond_report`. The hub records the run,
  audits (`scheduled_task_run` with `{schedule_id, status, catch_up?}`), and may
  drop an Inbox notification and/or a kanban card (ties into Epic 07's `origin`:
  `{"kind":"schedule","id":schedule_id}`).

**Trusted-input nuance (the key security difference from auto-respond).** Auto-respond
runs `--strict-mcp-config` with **no ampla MCP** because the input is an untrusted
incoming message (ARCHITECTURE Threat 1). A scheduled task's prompt is
**owner-authored and stored server-side** — trusted — so this is the one path where
an agent *may* be granted MCP/tools deliberately, per the schedule's `tools` preset.
**Decision:** default preset is still read-only and `--strict-mcp-config` with no
MCP; granting tools/MCP to a scheduled agent is the danger-zone case (8.5). This
keeps the safe default while enabling the powerful use case explicitly.

**Offline + control gates.** If the agent is offline at fire time, the run is
**skipped** (`last_status=skipped_offline`, audited) rather than queued — a stale
task firing on a much-later reconnect is surprising; re-anchor to the next slot.
The **global kill switch** and **per-agent pause** (Epic 03) suppress scheduled
runs just like auto-respond. Scheduled runs that *send messages* carry the existing
`[auto]`/system prefix so they can't trigger an auto-respond loop. Per-agent rate
limit applies.

**Security.** The daemon validates the frame (Zod), runs under the schedule's
guardrail preset, and attributes the run to the authenticated socket. The hub
re-checks ownership before sending. A revoked agent key ⇒ daemon offline ⇒ task
skipped. Every fire is audited; the run summary is treated as agent-authored
(sanitized like any agent text if surfaced).

**Tests.** Bridge: daemon handles a `scheduled_task` frame → runs the (fake) runner
with the preset's tools → emits `scheduled_task_report`; a paused/kill-switched
agent does not run; offline path. Hub: a due job for an online agent sends the
frame; offline → `skipped_offline`; report records the run + audit; kill switch
suppresses. Golden `ws_frames.json`. **Full-stack** (the `tests/e2e` lane): a real
hub fires a real scheduled task to a real daemon with a fake claude runner,
end-to-end.

**Effort.** ~2.5 days.

---

## 8.5 Web UI — schedule management · `◻ planned` · risk: low-med

**Goal.** Per-agent schedule management in the panel, all via `src/lib/api` +
`src/lib/ws` (components never `fetch`).

- In the agent detail (`web/src/features/agents/*`, alongside presets/DND/
  escalation/delegation), an **"Agendamentos"** section: list schedules with
  next/last run + status, create/edit (name, a friendly **cron/interval picker**,
  the task prompt, the guardrail preset), enable/disable toggle, **run-now**, and
  delete.
- **Danger-zone confirm** (reuse `DangerAction`) when the chosen preset grants
  write or MCP/tool access to the scheduled agent — granting an unattended agent
  tools is exactly the kind of guardrail-relaxation the danger-zone exists for.
- Live status via a `schedule` delta (or refetch on `scheduled_task_report`).

**Tests.** vitest/RTL: renders schedules with next/last run; create calls the API
with the right spec; the danger-zone appears for a write/tool preset; run-now hits
the endpoint; disable toggles without delete.

**Effort.** ~2 days.

---

## Deferred to a follow-up (noted, not built)

- **APScheduler / Postgres-backed jobs** for multi-process deploys (needs the
  Postgres profile, suggestion #6) — v1 is single-process by design.
- **Calendar/timezone-per-schedule UI** (v1 is UTC with a friendly picker).
- **Chaining a schedule to a kanban pipeline** (overlaps Epic 07 deferred
  auto-chaining).
- **Queue-on-reconnect** for offline agents (v1 skips; revisit if users want
  "catch up when I come back").

---

## Epic 08 milestone checklist

- [ ] 8.1 Scheduler engine (tick loop, claim-before-fire, catch-up collapse, pure
  `next_run` helper) — unit + engine tests
- [ ] 8.2 Maintenance sweeps folded in as internal recurring jobs (startup
  catch-up retained) — audited counts
- [ ] 8.3 `agent_schedules` model + CRUD + ownership authz + min-interval + golden
  openapi
- [ ] 8.4 `scheduled_task` / `scheduled_task_report` frames (mirror + ws_frames
  golden); daemon reuses the claude runner + guardrails; offline/kill-switch/pause
  gates; full-stack e2e
- [ ] 8.5 Per-agent schedule UI + cron/interval picker + danger-zone for tool
  access + run-now
- [ ] Every fire audited; trusted-prompt vs. tool-grant boundary enforced; the
  `[auto]` anti-loop prefix on scheduled sends
- [ ] UI exposes the full schedule surface (standing "UI covers backend" rule)

Recommended order: 8.1 → 8.2 (proves the engine on safe internal jobs) → 8.3 →
8.4 (the hard, security-critical slice) → 8.5.

---

## Sources

- Cron/recurrence semantics (catch-up / misfire grace — the problem APScheduler
  formalizes, which we mirror minimally):
  https://apscheduler.readthedocs.io/en/3.x/userguide.html#missed-job-executions-and-coalescing
- Ampla auto-respond threat model (`--strict-mcp-config`, untrusted-input rule):
  [`../ARCHITECTURE.md`](../ARCHITECTURE.md), [`03-autorespond-trust.md`](03-autorespond-trust.md)
- Epic 04 delegation/runner reuse: [`04-agent-policy.md`](04-agent-policy.md)
