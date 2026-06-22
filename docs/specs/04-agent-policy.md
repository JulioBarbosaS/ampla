# Epic 04 — Agent Config & Policy

Higher-level controls layered on the agent settings model. Builds on the
guardrail fields (`allow_write`, `block_*`, `denied_paths`, `trusted_senders`),
the auto-respond pipeline, and (for routing) the Inbox (Epic 02).

Files in play: `hub/app/models/agent.py`, `hub/app/schemas/agent.py`,
`hub/app/services/agent_service.py`, `hub/app/api/routes/agents.py`,
`bridge/src/daemon/auto-responder.ts` + `index.ts`, `web/src/features/agents/*`.

---

## 4.1 Reusable guardrail presets · `◻ planned` · risk: med

**Goal.** Stop reconfiguring the same guardrails per agent. Define named
**presets** (a bundle of the security/auto settings) and apply one to an agent;
optionally keep the agent **linked** to the preset so edits propagate.

**Model.** New table `guardrail_presets`:
| column | type | notes |
|---|---|---|
| `id` | int PK | |
| `owner_id` | int FK→users.id, nullable | null = built-in/global (admin-managed) |
| `name` | str(60) | unique per owner |
| `settings` | json | the guardrail/auto subset: `allow_write, block_hidden_files, block_sensitive_paths, confine_to_dir, denied_paths, trusted_senders, mode, max_auto_per_hour, auto_timeout_secs, require_approval, auto_paused, budgets` |
| `created_at` | UTCDateTime | |

Link option: add `preset_id: int | null` to `agents` (default null). If set, the
agent **inherits** the preset’s settings (preset is source of truth); explicit
per-agent overrides stored as a sparse JSON diff (`settings_override`), applied
on top. v1 can ship **apply-and-detach** (copy preset → agent fields, no live
link) to avoid the inheritance complexity, then add linking in v1.1.

**Built-in presets to seed** (matching the danger tiers we discussed):
- **Estrito (padrão)** — read-only, all blocks on, confined, no trusted senders.
- **Leitura ampla** — read-only but `confine_to_dir` off.
- **Escrita confinada** — `allow_write` on, all blocks on (requires sandbox).
- **Confiável (perigo)** — guardrails relaxed for `trusted_senders` — gated by
  the existing danger-zone triple-confirm in the UI.

**Endpoints.** `GET/POST /api/guardrail-presets`, `PATCH/DELETE
/api/guardrail-presets/{id}` (owner/admin; built-ins admin-only), and
`POST /api/agents/{slug}/apply-preset {preset_id}`. Applying triggers the usual
`settings_update` push to the daemon.

**Web.** A preset picker on the agent card ("Aplicar preset") + a presets manager
(list/create/edit) in settings. Built-in "Confiável" keeps the red danger-zone
treatment.

**Security.** Presets centralize the **most dangerous** knobs (`trusted_senders`,
`allow_write`) — applying a permissive preset is a privileged action: audited
(`preset_applied`) and, for trusted-sender presets, behind the danger-zone
confirm. Validate `denied_paths` with the existing `_clean_denied_paths` rules at
preset save time too.

**Tests.** Service: create/apply preset writes the agent fields + pushes settings;
applying a trusted preset is audited; cross-owner preset isn’t applicable.
Integration: endpoints + authz. Golden: openapi. Web: picker applies, danger
confirm for trusted preset.

**Effort.** ~2 days (apply-and-detach); +1 day for live linking.

---

## 4.2 Availability window / DND · `◻ planned` · risk: low

**Goal.** Auto-respond only inside configured hours; outside, behave like
`inbox` (enqueue, notify, no `claude -p`).

**Model.** Add to `agents` + `AgentSettings`:
- `auto_schedule: json | null` (default null = always-on). Shape:
  `{tz: "America/Sao_Paulo", windows: [{days:[1..7], start:"09:00", end:"18:00"}]}`.
  Keep it small and validated (≤N windows, valid HH:MM, IANA tz).

**Enforcement (daemon).** In `maybeAutoRespond`, after the kill-switch/pause
checks: if `auto_schedule` is set and "now" (in the schedule tz) is outside all
windows → `result=skipped`, reason `outside_hours`; the message still enqueues
and (Epic 02) notifies. Use an injectable clock (the daemon already passes `now`
to the auto-responder) so it’s testable.

**Web.** A simple schedule editor on the agent (day checkboxes + start/end +
timezone, default the browser tz). Show a "fora do horário" hint when applicable.

**Security.** Purely a throttle; reduces off-hours auto-respond exposure. No new
untrusted surface. Validate tz/format server-side (reject junk).

**Tests.** Bridge unit (injectable clock): inside window → runs; outside →
skipped `outside_hours`; tz handling; malformed schedule rejected at the hub
schema. Golden: AgentSettings field.

**Effort.** ~1 day.

---

## 4.3 Escalation to human inbox · `◻ planned` · risk: med · **depends on Epic 02**

**Goal.** When an agent can’t/shouldn’t answer, route the message to the owner’s
**Inbox** instead of dropping it — so nothing addressed to an agent is silently
lost.

**Triggers.**
- Auto-respond `result=failed` (timeout, crash) or `blocked` (secret filter).
- `result=skipped` for `rate_limit` / `budget_exceeded` / `outside_hours`.
- Optional: an explicit "não sei responder" signal the model can emit (a sentinel
  the daemon detects in the reply, e.g. `__ESCALATE__`) → escalate instead of
  sending.
- Inbox-mode agents: any incoming `request`/`task` already enqueues; escalation
  just guarantees a notification with reason `escalation`.

**Mechanism.** Reuses Epic 03’s report frame + Epic 02’s notifications: on the
trigger, the hub creates a notification (reason `escalation`) for the owner,
linking to the original message and (if any) the failure reason / partial draft.
Add a per-agent setting `escalate_on: list[str]` (default `["failed","blocked"]`)
so owners choose which outcomes escalate.

**Web.** Escalations appear in the Inbox; from there the owner can reply manually
(as the agent) using the normal composer — closing the loop.

**Security.** No new external surface; it’s internal routing. Avoid escalation
storms: collapse repeated escalations on the same `subject_key` (Epic 02 grouping
already does this) + respect the per-user generation cap.

**Tests.** Hub: each trigger creates the right notification (mock report frame);
`escalate_on` filters which outcomes escalate; collapsing on repeats. Bridge:
the `__ESCALATE__` sentinel path. Golden: setting field.

**Effort.** ~1.5 days (mostly glue once 02 + 03 exist).

---

## 4.4 Agent-to-agent delegation / handoff · `◻ planned` · risk: med/high · largest

**Goal.** An agent can hand a task to another agent **with context**, and the
result comes back — multi-agent workflows without a human relaying.

**Model.** New table `delegations`:
| column | type | notes |
|---|---|---|
| `id` | int PK | |
| `from_agent` / `to_agent` | str(60) | delegator / delegate |
| `root_message_id` | int | the originating message |
| `context` | text | the handed-over context (bounded; sanitized) |
| `status` | str(12) | `open \| accepted \| completed \| declined \| expired` |
| `result_message_id` | int \| null | the delegate’s answer |
| `created_at` / `updated_at` | UTCDateTime | |

**Protocol.** A delegation is modeled as a **message with `type:"task"`** plus a
`delegation_id` link, so it flows through the existing routing/allowlist/threading
— minimal new surface. Add `delegation_id: int | null` to the message send frame
+ `MessageOut` (mirror + golden) **or** keep delegation purely as a hub-side
association keyed by `root_message_id` (no wire change) — **prefer the latter for
v1** to avoid touching the hot message frame.

**Flow.** `from_agent` calls (via MCP tool `amp_delegate` — new) → hub creates a
`delegations` row + sends a `task` message to `to_agent`. The delegate (auto or
human-assisted) replies in-thread; the hub marks the delegation `completed` and
notifies the delegator (reason `task_assigned`/`state_change`). Allowlist still
applies (a delegate that blocked the delegator → `declined`).

**MCP.** New stateless MCP tool in `bridge/src/mcp/` (`amp_delegate {to, task,
context}`) that calls the daemon local API, which sends via the WS client. Keep
the daemon as the only WS owner (contract).

**Security.** Delegation is **agent-initiated** → it must obey the same trust
rules: the delegate’s allowlist gates it; the handed `context` is untrusted to
the delegate (delimited in its prompt, like any incoming message); guardrails of
the **delegate** apply to its run; loop/hop guards extend across delegations
(count delegation hops toward `MAX_AUTO_REPLIES_PER_THREAD` to prevent
agent↔agent runaway). Cap delegation depth/fan-out per thread.

**Web.** A delegation view (who handed what to whom, status) per thread; the
Inbox shows delegation assignments/results.

**Tests.** Hub: delegate creates row + task message; completion links result +
notifies; allowlist-blocked delegate → declined; depth cap. Bridge: `amp_delegate`
MCP → daemon → WS send; hop guard counts delegations. Golden: openapi (+ message
frame if the field is added).

**Effort.** ~3–4 days (multi-tier, new MCP tool, loop-safety). Ship last.

---

## Epic 04 milestone checklist

- [x] 4.1 Guardrail presets — table + endpoints + apply + built-ins + card picker
  (`8d7bcd0` backend, `c4e7c54` web; danger-zone for permissive presets)
- [x] 4.2 Availability/DND — `auto_schedule` + daemon `outside_hours` gate + editor
  (`c405392` backend+daemon, `8ecffb2` web)
- [x] 4.3 Escalation (settings + notification glue) — `escalate_on` + record_run
  routing + `__ESCALATE__` sentinel + card editor
  (`c2aecc0` hub, `6c97bbf` bridge, `7e9c09d` web)
- [x] 4.4 Delegation/handoff — `delegations` table + `delegate` frame + completion
  + `amp_delegate` MCP + `/delegate` daemon API + card view
  (`c3879d0` hub, `a32b7f8` bridge, `2f2d67b` web)
- [x] Every new dangerous knob is audited + behind the danger-zone where relevant

Recommended order: 4.2 (cheap) → 4.1 (presets) → 4.3 (needs Inbox) → 4.4 (biggest).

> **Epic 04 complete.** Loop-safety note for 4.4: agent↔agent runaway is
> structurally impossible — the auto-responder runs `claude -p
> --strict-mcp-config` with no `ampla` MCP, so an auto-reply can never call
> `amp_delegate`. Delegation is therefore human-in-the-loop; the per-thread
> auto-reply cap and a defensive open-delegation cap bound the rest.
