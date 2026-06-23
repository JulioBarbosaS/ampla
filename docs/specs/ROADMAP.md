# Ampla — Feature Specs Roadmap

Specs for the features selected in the planning session. Each epic doc is
self-contained: goal, data model + migration, REST/WS surface, bridge/daemon
changes, web/UI, security, tests, effort. These specs are a **proposal** — no
code is written until an epic is approved.

> Every spec obeys the contract in [`../ARCHITECTURE.md`](../ARCHITECTURE.md):
> hub layering (routes → services → repositories → models), the `ws.py` ↔
> `protocol.ts` mirror (change both in one commit + regenerate
> `hub/tests/golden/ws_frames.json`), new REST endpoints regenerate
> `openapi.json`, Alembic migrations backfill existing rows with
> `server_default`, and **every feature ships with a test in the same commit**.

## Epics

| # | Epic | Features | Closes debt? | Risk |
|---|---|---|---|---|
| [01](01-messaging-ux.md) | Messaging UX | Markdown + code blocks · Threads UI · Message TTL in UI · "Responding…" indicator | partial | Low |
| [02](02-user-inbox.md) | User Inbox (GitHub-style) | Notification model · triage (unread/saved/done) · reasons · subscriptions · filters · WS deltas | new | Med–High |
| [03](03-autorespond-trust.md) | Auto-respond Trust & Control | Auditable transcript · kill switch + per-agent pause · human approval (agent permission) · token/cost budget + metrics | new | Med |
| [04](04-agent-policy.md) | Agent Config & Policy | Guardrail presets · availability window / DND · escalation to human inbox · agent-to-agent delegation/handoff | partial | Med |
| [05](05-account-auth.md) | Account & Auth | `PATCH /api/auth/me` (name) · change password · avatar upload (server-side) · forgot-password reset | **yes** | Med |
| [06](06-kanban.md) | Kanban / Task Board | Boards/columns/cards + comments · fractional-rank ordering w/ concurrency control · per-agent per-board role grants (dev-only default) · `amp_kanban_*` MCP · WS deltas + inbox notifications · live board view | **yes** | Med–High |

### Follow-ups (from the project-suggestions list) — **done**

These three shipped after Epics 01–06; numbers in parentheses map to the
project-suggestions list discussed with the maintainer.

| # | Epic | Features | From | Risk |
|---|---|---|---|---|
| [07](07-kanban-lifecycle.md) | Kanban Lifecycle & Origin Linking | delegation-complete → card to Done · escalation resolution → Done · `origin` surfacing (card ↔ conversation) · conversation → card (fills `message`/`thread` kinds) | #10 | Med |
| [08](08-scheduled-agent-tasks.md) | Scheduled Agent Tasks | real scheduler engine (cron/interval) · maintenance sweeps folded in · `agent_schedules` model + CRUD · `scheduled_task` frame → daemon runs the agent · schedule UI | #9 (+#5) | Med–High |
| [09](09-release-engineering.md) | Release Engineering & Dev Hooks | version single-source + sync gate · pre-commit format + commit-msg validator · `release.sh` (cut/changelog/tag) · GitHub Release from CHANGELOG | #8 | Low–Med |
| [10](10-board-sharing.md) | Board Sharing | per-user board membership (share a private board with specific people) · members grant their **own** agents onto it | maintainer ask | Med · **planned, not built** |

> Epics 01–06 are **done**. Epic 06 shipped 6.1–6.6 (core data, race-safe
> ordering, per-agent permissions, MCP + agent-key reads, inbox integration,
> live board UI) plus the deferred follow-ups (event cards, grants/danger-zone
> UI, card detail + comments, full board/column management, card dependencies/
> DAG). Epics **07–09 are also done** (each spec's checklist links its commits);
> a few sub-items are noted as deferred follow-ups in their specs.
>
> CI/CD (suggestion #1) is partly in place already: `.github/workflows/ci.yml` +
> `release.yml` + `dependabot.yml` exist, and `scripts/ci.sh` + `.githooks/pre-push`
> run the same gates on plain local git today. Epic 09 builds the release ritual
> on top.

## Suggested sequencing & why

```
Phase 1  ── Epic 01 Messaging UX            (high perceived value, low risk, mostly web)
Phase 2  ── Epic 05 Account & Auth          (closes known debt; unblocks server-side avatar)
Phase 3  ── Epic 03 Auto-respond Trust      (security core: transcript, kill switch, approvals)
Phase 4  ── Epic 02 User Inbox              (consumes events from 01/03: mentions, approvals, autorespond-done)
Phase 5  ── Epic 04 Agent Config & Policy   (builds on settings + inbox; escalation needs the inbox)
```

### Dependency graph (key edges)

- **Inbox (02)** consumes notification sources produced by other epics:
  - `mention` → mention parsing introduced in **01** (Threads/Markdown).
  - `approval_requested` → human-in-the-loop in **03**.
  - `autorespond_completed` / `autorespond_blocked` → transcript in **03**.
  - `escalation` → **04** routes an un-handleable message into the inbox.
- **Human approval (03)** and **escalation (04)** both *produce* inbox notifications, so they’re cheaper to finish *after* the inbox exists — but each can ship a degraded path first (panel banner) and wire into the inbox once **02** lands.
- **Avatar upload server-side (05)** supersedes the current client-only localStorage avatar; the web `Avatar` component already abstracts the source, so the swap is contained.

## Cross-cutting conventions every epic follows

- **Migrations:** one Alembic revision per epic’s schema change, columns added with `server_default` so existing rows backfill (lesson from the guardrails migration). New tables get their own revision.
- **WS protocol changes:** new frames/fields land in `hub/app/schemas/ws.py` **and** `bridge/src/shared/protocol.ts` in the same commit; regenerate `ws_frames.json`; the bridge mirror test (`bridge/tests/golden/protocol-mirror.test.ts`) must stay green.
- **REST changes:** regenerate `hub/tests/golden/openapi.json` and review the diff.
- **Security posture:** new untrusted surfaces (rendered markdown, uploaded images, agent-authored notification text) are treated as hostile by default — see each epic’s Security section. Audit-worthy actions add an `audit_log` event.
- **Tests:** unit (services w/ fake repos), integration (TestClient REST+WS / Fastify inject), golden (contracts), web (vitest + snapshot), and a property test for any new rate-limiter/parser/filter.

## Status legend used in each epic

`◻ planned` · `◐ in progress` · `◼ done`. All items start `◻ planned`.
