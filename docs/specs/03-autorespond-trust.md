# Epic 03 — Auto-respond Trust & Control

The auto-responder is the highest-risk surface (Threat 1 in ARCHITECTURE.md):
an outsider’s message drives a headless `claude -p` on a developer’s machine.
This epic makes that **observable, controllable, and gated** — the trust pillar.

Files in play: `bridge/src/daemon/auto-responder.ts`, `bridge/src/daemon/index.ts`,
`bridge/src/daemon/ws-client.ts`, `bridge/src/shared/config.ts`,
`hub/app/services/agent_service.py`, `hub/app/schemas/agent.py`,
`hub/app/models/agent.py`, `hub/app/schemas/ws.py` + `bridge/.../protocol.ts`,
`hub/app/models/audit.py`.

---

## 3.1 Auditable auto-respond transcript · `◼ done` · risk: med

> Shipped in `1d3cbdc` (backend: `autorespond_runs` table, `AutorespondReportFrame`,
> daemon reporting, read endpoints) and `21b7b2b` (web: "Atividade automática" tab).
> Deviations from this spec, both deliberate: the record carries **no `agent_id`**
> (the hub attributes every run to the socket's authenticated slug — stronger
> anti-spoof than verifying a claimed id); and the **prompt is never stored**, even
> under `AMP_AUTORESPOND_FULL_TRANSCRIPT` (which only widens the reply preview) —
> the prompt holds owner instructions + conversation, already in message history.

**Goal.** For every auto-respond run, record an auditable entry: what triggered
it, the prompt context (or a redacted digest), the reply, **which tools/guardrails
were in effect**, exit status, duration, and token/cost when available. The owner
(and admin) can review exactly what each Claude did when poked from outside.

**Where the data is born.** Only the **daemon** sees the run. So the daemon
emits a transcript record to the hub, which persists it. Two options:

- **A. WS frame (recommended).** New client→hub frame
  `AutorespondReportFrame {type:"autorespond_report", record: AutorespondRecord}`
  sent by the daemon after each run. The hub stores it (new table) and may emit a
  `autorespond_completed`/`autorespond_blocked` **notification** (Epic 02).
- B. A local-API + REST push — heavier; A reuses the authenticated WS the daemon
  already owns. Go with A.

**`AutorespondRecord` (frame payload + stored row).**
| field | type | notes |
|---|---|---|
| `agent_id` | str | sender of the record = the responding agent (hub verifies it matches the socket’s authenticated agent) |
| `trigger_message_id` | int \| null | the incoming message that triggered it |
| `from_sender` | str | who poked the agent |
| `result` | enum | `replied \| blocked \| failed \| skipped` (mirrors `AutoRespondResult`) |
| `reason` | str \| null | skip/block/fail reason |
| `reply_preview` | str | first N chars of the reply (full reply already lives as a normal message) |
| `tools_allowed` | str | the `allowedTools` string used |
| `tools_disallowed` | str | the `disallowedTools` string |
| `guardrails` | json | snapshot: `{allow_write, block_hidden_files, …, trusted_sender: bool, sandbox: "host"\|"docker"}` |
| `duration_ms` | int | run wall-time |
| `timed_out` | bool | hit `auto_timeout_secs` |
| `input_tokens` / `output_tokens` / `cost_usd` | int/int/float, nullable | from `claude -p --output-format json` if parsed (see 3.4) |
| `created_at` | UTCDateTime | |

Stored in a new `autorespond_runs` table (hub), new Alembic revision. Indexed by
`(agent_id, created_at)`.

**Daemon work.** In `auto-responder.ts`, the `handle()` result already carries
`kind` + reason; extend it to also surface the guardrails snapshot, duration,
and (3.4) token usage. `daemon/index.ts` sends the report frame after handling.
`runProcess`/runner returns timing; switch `claude -p` to `--output-format json`
to capture usage (parse defensively; fall back to text).

**Privacy.** The **prompt is not stored verbatim** by default (it can contain
the operator’s instructions + conversation). Store `reply_preview` + metadata;
the full reply is already a normal message in history. Add an opt-in
`AMP_AUTORESPOND_FULL_TRANSCRIPT` for debugging that stores the full prompt/reply
(documented as sensitive).

**Hub.** New `AutorespondService` + repo + read endpoints:
`GET /api/agents/{slug}/autorespond-runs?limit=` (owner/admin) and an
admin-wide `GET /api/autorespond-runs`. The hub **verifies** the reporting
socket owns `agent_id` (anti-spoof, like `ack`).

**Web.** A "Atividade automática" tab on the agent (in `AgentCard`/agent detail):
a table of runs with result chips, guardrail snapshot, duration, tokens/cost,
link to the resulting message.

**Tests.** Bridge unit: `handle()` populates the record for each result kind.
Hub integration: report frame persists a row; non-owning socket reporting another
agent is rejected; read endpoints authz. Golden: `ws_frames.json` (+`openapi.json`).

**Effort.** ~2 days.

---

## 3.2 Kill switch + per-agent pause · `◼ done` · risk: low/med — high security payoff

> Shipped in `3e36595` (per-agent `auto_paused` fast brake) and `5be0024`
> (global admin kill switch: persisted `hub_state`, `KillSwitchFrame` +
> `auto_responder_enabled` in `hello_ack`, real-time broadcast, panel banner).

**Goal.** Instant containment. Two levels:
- **Per-agent pause:** owner flips the agent out of auto temporarily.
- **Global kill switch:** admin pauses **all** auto-responders instance-wide.

**Model.**
- Per-agent: add `auto_paused: bool` (default false) to `agents` +
  `AgentSettings`/`AgentSettingsUpdate` (mirror in `protocol.ts`). When true, the
  daemon treats the agent as `inbox` regardless of `mode` (messages enqueue, no
  `claude -p`). Reuses the existing `settings_update` push — flip is real-time.
- Global: add `auto_responder_enabled: bool` (default true) to hub settings
  **and** broadcast a new hub→client frame `KillSwitchFrame {type:"kill_switch",
  auto_responder_enabled: bool}` to all daemons on change. The daemon gates
  `maybeAutoRespond` on this flag. Persist the global flag so it survives
  restart (a tiny `hub_state` table or a settings row).

**Endpoints.**
- Per-agent: already covered by `PATCH /api/agents/{slug}/settings` (add field).
- Global: `POST /api/admin/kill-switch {enabled: bool}` (admin-only; audited as
  `kill_switch_toggled`). Reflect state in `GET /api/admin/kill-switch`.

**Web.**
- Per-agent: a prominent **Pausar auto-resposta** toggle on the agent card
  (distinct from the mode select — it’s a fast brake).
- Global: a red control in the admin/Team area (or settings) — "Pausar TODAS as
  respostas automáticas", with the danger-zone treatment already used for
  sensitive toggles. Banner in the panel when the kill switch is engaged.

**Daemon.** Gate order in `maybeAutoRespond`: global kill switch → per-agent
`auto_paused` → existing layers (`[auto]` prefix, type, hop guard, rate limit).
On reconnect, the daemon learns both states (global via `hello_ack` — add the
flag there, or an immediate `kill_switch` frame; per-agent via the `settings`).

**Tests.** Hub: toggling global broadcasts `kill_switch`; admin-only. Bridge:
`maybeAutoRespond` skips when global off or `auto_paused`; resumes when cleared.
Golden: `kill_switch` frame + `hello_ack` field if added; `auto_paused` in
AgentSettings golden + openapi.

**Effort.** ~1.5 days.

---

## 3.3 Human-in-the-loop approval (agent permission) · `◼ done` · risk: med

> Shipped across `fa65cde` (require_approval setting), `e665d5d` (approval
> request frame + persist + owner notice), `56bfda3` (decision flow: approve/
> edit/reject + server-side send + expiry), `9764dc3` (daemon drafts & requests
> instead of sending), `3218939` (web: toggle + Pendências decide UI). Deviation:
> a needs_approval draft is audited as a pending approval (the approvals table),
> not as an autorespond_runs transcript row, to keep that result enum exact.

> Per the planning note: **this is a permission in the agent’s options** — not a
> global mode. An agent can be set to require the owner’s approval before its
> auto-reply goes out.

**Model.** Add to `agents` + `AgentSettings`:
- `require_approval: bool` (default false). When true and `mode=auto`, the
  auto-responder **drafts** the reply but does **not** send it.

**Flow.**
1. Daemon runs `claude -p` as usual (guardrails apply). Instead of sending the
   `[auto]` reply, it sends a new client→hub frame
   `ApprovalRequestFrame {type:"approval_request", trigger_message_id, to,
   draft_body, record_ref}`.
2. Hub persists a **pending approval** (new `approvals` table: id, agent_slug,
   trigger_message_id, to_agent, draft_body, status `pending|approved|rejected|edited`,
   decided_by, decided_at, created_at) and creates an Epic-02 notification
   `approval_requested` for the owner.
3. Owner reviews in the panel: **Aprovar**, **Editar e enviar**, or **Rejeitar**.
   - Approve/Edit → hub sends the (possibly edited) message as the agent via the
     existing send path, marks the draft delivered, notifies.
   - Reject → no message sent; recorded + audited.
4. Hub→daemon frame `ApprovalDecisionFrame` is optional (the hub sends the
   message itself; the daemon doesn’t need to act). Keep the send server-side so
   approval works even if the daemon later disconnects.

**Why gate the reply, not individual tool calls.** Headless `claude -p` has no
interactive per-tool prompt; the safe, shippable gate is the **outgoing reply**.
Write/edit actions are already gated by `allow_write` + the Docker sandbox.
*Future:* a `PreToolUse` hook in a sandboxed interactive runner could gate tool
calls — noted, not in v1.

**Endpoints.** `GET /api/agents/{slug}/approvals?status=pending` (owner/admin),
`POST /api/approvals/{id}/decision {decision:"approve"|"reject", body?}`
(owner/admin; audited `approval_decided`).

**Web.** Approvals surface in the **Inbox** (reason `approval_requested`) and in
a per-agent "Pendências" list: shows the incoming message, the agent’s draft (as
read-only Markdown), and the three actions. Editing reuses the composer.

**Security.** The draft is agent-authored → render as sanitized Markdown
(Epic 01 rules). Only the agent’s owner or an admin can decide. The draft reply
is **scanned by the secret filter before it’s ever shown/sent** (same as today).
Approvals expire (config TTL) → auto-reject + notify, so nothing hangs forever.

**Tests.** Bridge: with `require_approval`, `handle()` returns a draft and emits
`approval_request` instead of sending. Hub: draft persists + notification
created; approve sends as agent; edit sends edited; reject sends nothing; authz;
expiry auto-rejects. Golden: frame(s) + endpoints.

**Effort.** ~2–3 days (couples with Epic 02 for the nicest UX; can ship with a
panel banner first).

---

## 3.4 Token/cost budget + usage metrics · `◼ done` · risk: low/med

> Shipped in `9a32a02`. Deviation: usage capture (`claude -p --output-format
> json`) is **opt-in** via the daemon's `capture_usage` (default off) so the
> validated text-mode flow is untouched and a JSON-shape mismatch can't regress
> the live path (it fails the run, never sends raw JSON). The daily budget is
> therefore inert until capture is enabled — surfaced in the UI.

**Goal.** Per-agent visibility and a hard ceiling on auto-respond spend.

**Capture.** Run `claude -p --output-format json` and parse `usage`
(input/output tokens) + cost; store on each `autorespond_runs` row (3.1).
Defensive parsing — fall back to text mode and null usage if the shape changes.

**Budget.** Add to `agents` + `AgentSettings`:
- `max_auto_tokens_per_day: int | null` (default null = unlimited) and/or
  `max_auto_cost_usd_per_day: float | null`.
- The daemon tracks a rolling daily counter (like the existing hourly
  `allowByRate`); when the budget is exceeded, auto-respond is **skipped**
  (`result=skipped`, reason `budget_exceeded`) and a notification fires. Counter
  resets at local midnight; persisted across restart via the local store so a
  bounce can’t reset the budget.

**Metrics.** A small per-agent dashboard (reuse 3.1’s runs table): runs/day,
tokens/day, cost/day, block/fail rate. Optionally expose a Prometheus endpoint
later (cross-cut with the ops epic — out of scope here).

**Security.** Budget is also an **anti-abuse** control — caps the blast radius of
a flood of malicious messages even within the hourly limit. Document that
token/cost from the CLI are best-effort (provider-reported).

**Tests.** Bridge: budget counter blocks past the ceiling, resets at day
boundary (injectable clock — add a property test alongside the existing rate-limiter
properties), persists across restart. Hub: usage fields persist + surface.

**Effort.** ~1.5 days (builds directly on 3.1).

---

## Epic 03 milestone checklist

- [x] 3.1 Transcript: `autorespond_runs` table + report frame + read endpoints + agent activity tab
- [x] 3.2 Kill switch (global frame + admin endpoint) + per-agent `auto_paused`
- [x] 3.3 Human approval: `require_approval` setting + `approvals` table + request frame + decision endpoint + daemon gate + UI
- [x] 3.4 Budget + usage: `--output-format json` parsing + daily caps + metrics
- [ ] All WS/REST changes regenerate goldens; new limiter/parser gets a property test

Recommended order: 3.2 (fast safety win) → 3.1 (observability) → 3.4 (budget, on top of 3.1) → 3.3 (approvals, nicest after Epic 02).
