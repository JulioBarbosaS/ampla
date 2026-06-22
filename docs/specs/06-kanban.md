# Epic 06 — Kanban / Task Board

A shared team board where **humans (devs) and AI agents collaborate** on cards,
woven into Ampla's existing fabric: agents act on it through new MCP tools (the
`amp_delegate` pattern), changes stream live over the WS (like the chat), and
the board is gated by a **per-agent, per-board permission model**. The headline
requirement: a board can be **dev-only**, or selected agents can be granted
rights to **create / move / edit** cards — never more than the owner allows.

Files in play: `hub/app/models/kanban.py`, `hub/app/schemas/kanban.py`,
`hub/app/services/kanban_service.py`, `hub/app/repositories/kanban_repo.py`,
`hub/app/api/routes/kanban.py`, `hub/app/schemas/ws.py`,
`bridge/src/mcp/index.ts`, `bridge/src/daemon/local-api.ts` + `ws-client.ts` +
`index.ts`, `bridge/src/shared/protocol.ts`, `web/src/features/kanban/*`.

> Builds on: the identity model (users + agent keys), the per-agent permission
> conventions (`allowed_senders`/`trusted_senders`), anti-spoof socket
> attribution, the `audit_log`, the Inbox (Epic 02), and delegation/escalation
> (Epic 04).

## Prior art & references (why these choices)

Two families exist. **(A) Agent-runner boards** (vibe-kanban, Cline Kanban,
DanWahlin/ai-agent-board, Claw-Kanban, saltbo/agent-kanban, kandev) — cards drive
coding agents that run in git worktrees and open PRs. **(B) MCP-exposed shared
boards** (bradrisse/kanban-mcp↔Planka, eyalzh/kanban-mcp, tcarac/taskboard,
Raman369AI/agent-kanban-pm, quentintou/agent-board) — humans and agents read/write
a board over MCP. **Ampla is family B**, but multi-user and security-first.

Adopted from prior art: append-only audit trail and per-agent identity
(agent-board); WIP limits enforced on move (kanban-mcp); comments-as-thread and a
"my tasks" filter (agent-board); default columns backlog→todo→doing→review→done.
Card ordering follows **LexoRank/fractional indexing** (Jira), and concurrency
follows the **lock-then-recompute-in-transaction** pattern (see §6.2 sources).

What Ampla adds over prior art: real **permission tiers per agent per board**
(most prior art has identity but no RBAC), the **auto-respond-can't-touch-the-board**
guarantee (`--strict-mcp-config`), anti-spoof + the secret-filter + a danger-zone
for granting write to an AI, and **integration** with messages/inbox/delegation.

DAG dependencies + cycle detection and quality gates (`requiresReview`) are
notable agent-board features deferred to **v2** (see §6.7).

---

## 6.1 Board, columns, cards & comments · `◻ planned` · risk: med

**Goal.** The core data + REST CRUD for boards, columns, cards and card
comments. Humans manage via the panel; agents via MCP (§6.4). All reads/writes
are authorized per §6.3.

**Model.** New tables (one Alembic revision; new tables, no backfill needed):

`kanban_boards`
| column | type | notes |
|---|---|---|
| `id` | int PK | |
| `owner_id` | int FK→users.id | creator; full control |
| `name` | str(120) | |
| `visibility` | str(8) | `team` \| `private` (private = owner + grantees) |
| `default_agent_role` | str(12) | role an agent gets with no explicit grant; default `none` (= dev-only) |
| `created_at` | UTCDateTime | |

`kanban_columns`
| column | type | notes |
|---|---|---|
| `id` | int PK | |
| `board_id` | int FK | |
| `name` | str(60) | |
| `rank` | str(64) | column order (same scheme as cards, §6.2) |
| `wip_limit` | int \| null | max cards; null = unlimited |
| `is_landing` | bool | new cards/event-cards land here (exactly one per board) |

`kanban_cards`
| column | type | notes |
|---|---|---|
| `id` | int PK | |
| `board_id` | int FK | denormalized for fast board reads + authz |
| `column_id` | int FK | |
| `rank` | str(64) | order WITHIN the column (§6.2) |
| `title` | str(200) | |
| `body` | text | bounded (`KANBAN_CARD_BODY_MAX`, e.g. 16 KiB) |
| `created_by` | str(60) | **AUTHENTICATED actor** — `user:<id>` or agent slug (anti-spoof) |
| `assignee` | str(60) \| null | agent slug or `user:<id>` |
| `priority` | str(8) | reuses the message PRIORITY_PATTERN |
| `origin` | json \| null | `{kind: message\|thread\|delegation\|escalation, id}` (§6.5) |
| `version` | int | optimistic-concurrency counter (§6.2); bumped on every mutation |
| `created_at` / `updated_at` | UTCDateTime | |

`kanban_card_comments`
| column | type | notes |
|---|---|---|
| `id` | int PK | |
| `card_id` | int FK | |
| `author` | str(60) | authenticated actor (anti-spoof) |
| `body` | text | bounded; agent-authored → stored plain, rendered sanitized Markdown |
| `created_at` | UTCDateTime | |

A board is seeded with the default columns (Backlog / A fazer / Fazendo /
Revisão / Concluído), `is_landing` = "A fazer".

**Endpoints (REST).** `GET/POST /api/kanban/boards`, `GET/PATCH/DELETE
/api/kanban/boards/{id}`, `GET /api/kanban/boards/{id}/full` (board + columns +
cards in one payload for the initial render), column CRUD under the board, card
CRUD (`POST .../cards`, `PATCH/DELETE .../cards/{id}`), comments
(`GET/POST .../cards/{id}/comments`). Move is its own endpoint (§6.2). All go
through `KanbanService`, which enforces §6.3 authz; routes never touch repos.

**Security.** `created_by`/`author` are the authenticated identity (JWT user or
WS socket slug), never client-claimed. Card/comment bodies are untrusted
(agent- or human-authored) → stored as plain text, rendered as sanitized
Markdown (same treatment as approval drafts / messages). Sizes bounded.

**Tests.** Service unit (CRUD + authz with fake repos); integration (REST +
authz, cross-user board is 404/403 per surface convention); golden `openapi.json`.
Web: board renders columns+cards from `/full`.

**Effort.** ~2 days.

---

## 6.2 Card ordering & concurrency (race-condition core) · `◻ planned` · risk: high

**Goal.** Reorder cards within/across columns so a move is **O(1)** (rewrites
only the moved card) and **concurrent moves never corrupt the order or lose an
update**. This is the highest-risk slice; it gets the most tests.

**Ordering scheme — fractional rank (LexoRank-style).** `rank` is a short
lexicographically-sorted string. A move computes the **midpoint string** between
the neighbours at the destination; only the moved card's `rank` changes. Average
rank length stays tiny (~2–3 chars for hundreds of cards). [Jira LexoRank;
fractional indexing — see Sources.] A pure `compute_rank(before, after)` helper
(no I/O) holds the algebra and is property-tested.

**Anchor-based intent, not absolute position.** A move request says **"card C,
into column X, between `before_id` and `after_id`"** (the neighbours the client
saw) plus C's **expected `version`** — never a raw numeric index. The server
recomputes the rank from the *current* neighbours inside the transaction, so a
stale client view can't silently misorder.

**Concurrency model (defense in depth).**
1. **Serialized write transaction.** Every mutation runs in one DB transaction.
   SQLite serializes writers (one writer at a time via `BEGIN IMMEDIATE`), so two
   moves cannot interleave — this *is* the pessimistic lock the literature
   recommends for boards, for free. The rank is computed from neighbours re-read
   **inside** the transaction.
2. **Optimistic version check.** The move carries C's expected `version`; if it
   no longer matches (the card moved/edited under the client), the hub returns
   **409 Conflict** with the fresh card; the client refetches and retries. Same
   for card edits. Prevents lost updates.
3. **Unique `(column_id, rank)` index** as a backstop: on the rare midpoint
   collision the insert fails → bounded retry (recompute with a fresh midpoint /
   jitter, ≤3 attempts) → if still colliding, rebalance the column then retry.
4. **WIP limit enforced inside the transaction.** Moving into a full column is
   rejected (409/422) using the count read *within* the txn — never a stale
   pre-check (a classic TOCTOU race).
5. **Convergence.** After commit, the hub broadcasts a `kanban_delta` (§6.5);
   every observer reconciles to the authoritative state, so transient client
   divergence self-heals.

**Rebalance.** When a column's max rank length exceeds a cap
(`KANBAN_RANK_LEN_MAX`, e.g. 64) — or the backstop trips — `rebalance_column`
re-spreads ranks evenly in one transaction and bumps affected versions. Run
on-demand (cheap for a local hub); no background scheduler in v1.

**Endpoint.** `POST /api/kanban/cards/{id}/move`
`{to_column_id, before_id?, after_id?, expected_version}` → moved card or 409.
Mirror via the WS `kanban_action` (§6.5) for agents.

**Security.** Move authz per §6.3 (needs `contributor`+ for the card, or `editor`
on the board). The actor is the authenticated identity. Mutation rate-limited per
actor (anti-flood / agent runaway).

**Tests.**
- **Unit (pure):** `compute_rank` — midpoint is strictly between; first/last/empty
  cases; idempotent ordering.
- **Property (hypothesis):** for any random sequence of inserts/moves, the
  resulting `rank` order equals the intended logical order (the core invariant);
  ranks stay unique within a column; length stays bounded or rebalance fires.
- **Concurrency simulation:** two moves targeting the same gap, applied through
  the service against one in-memory DB, end deterministically (both ordered, no
  duplicate rank, no lost card); the second sees 409 or a clean re-rank.
- **WIP TOCTOU:** concurrent moves into a column at its WIP limit — only the
  allowed number land; the rest get rejected (count checked in-txn).
- **Integration:** move via REST returns 409 on stale `version`; rebalance keeps
  order; golden `ws_frames.json` for `kanban_action`/`kanban_delta`.

**Effort.** ~2.5 days (the algebra + the property/concurrency tests are the bulk).

---

## 6.3 Permission model (per-agent, per-board) · `◻ planned` · risk: med

**Goal.** The headline feature: a board is **dev-only** by default; selected
agents can be granted the right to **create / move / edit**. Roles are **per
board** (trust an agent on one board, not another) and apply only to **agents** —
human members keep full edit.

**Model.** `kanban_agent_grants`
| column | type | notes |
|---|---|---|
| `board_id` | int FK | |
| `agent_slug` | str(60) | |
| `role` | str(12) | `viewer` \| `contributor` \| `editor` |
| unique `(board_id, agent_slug)` | | |

**Roles** (agents only):
| role | capabilities |
|---|---|
| `none` (no grant + `default_agent_role=none`) | no access — **dev-only board** |
| `viewer` | read board + cards + comments; comment |
| `contributor` | + create cards, move/edit **own or assigned** cards |
| `editor` | + move/edit/delete **any** card, manage columns |

**Humans:** the board owner has full control; team members (per `visibility`)
have `editor`-equivalent. Permissions only ever *restrict agents*.

**Resolution.** `KanbanService.capability(actor, board, action)` →
`grant.role` for an agent, else `board.default_agent_role`; humans resolved via
ownership/visibility. Enforced at the **service layer** for every mutation —
never trusted from the daemon/client (same authority model as the message
allowlist).

**Endpoints.** `GET/PUT/DELETE /api/kanban/boards/{id}/grants` (owner/admin
only). A grant of `editor` (or `contributor`) to an agent is a **privileged
action**: audited (`kanban_grant_set`) and, in the UI, behind the **danger-zone
confirm** — consistent with `trusted_senders`. Granting write to an AI is treated
like relaxing a guardrail.

**Security.** Anti-spoof actor; service-layer enforcement; audit on every grant
change. A revoked/missing grant + `default_agent_role=none` ⇒ the agent's MCP
calls 403 at the hub even if its daemon tries.

**Tests.** Unit: capability matrix (each role × action); `contributor` can't
touch others' cards; dev-only board rejects all agent mutations; owner/admin-only
on grant management; cross-board grant doesn't leak. Integration: agent WS action
blocked by role → error frame; golden openapi (grants + role enum). Web: grant
panel, danger-zone for editor/contributor.

**Effort.** ~1.5 days.

---

## 6.4 Agent access via MCP · `◻ planned` · risk: med

**Goal.** Let an **interactive** agent session act on the board through MCP, and
guarantee an **auto-responding** agent cannot.

**MCP tools** (new, `bridge/src/mcp/`, mirroring `amp_delegate`): `amp_kanban_boards`
(list visible boards), `amp_kanban_cards {board}` (read; supports `mine=true` →
"my tasks"), `amp_kanban_create_card {board, column?, title, body?}`,
`amp_kanban_move_card {card, to_column, before?, after?}`,
`amp_kanban_comment {card, body}`. Each → daemon local API (`/kanban/...`, 0600
unix socket) → `kanban_action` WS frame → hub, which enforces §6.3.

**Structural safety (the key guarantee).** The auto-responder runs
`claude -p --strict-mcp-config` with **no ampla MCP** (docs/ARCHITECTURE.md ·
Threat 1). So an untrusted incoming message can **never** drive a board mutation —
board edits via MCP are only possible from a human-operated interactive session.
This is the same guarantee that makes delegation safe (Epic 04 · 4.4).

**Event-driven cards (no MCP).** The hub itself may create/update cards as a side
effect of trusted events — a **delegation** (4.4) creates a card in the landing
column assigned to the delegate; an **escalation** (4.3) creates a card flagged
"needs human". These are hub-side, not agent-driven, so they're safe regardless
of MCP. Gated by a board setting (`auto_card_on_delegation`/`_escalation`,
default off).

**Security.** Daemon `/kanban` validates payloads (Zod), requires a live hub
connection, attributes to the authenticated socket; the hub re-checks the
capability. Mutations count against a per-agent rate limit.

**Tests.** Bridge: `local-api` `/kanban/*` (frame emitted + validation 422s); MCP
smoke (`tools/list` includes the kanban tools; a tool routes a `kanban_action`).
Hub: a `kanban_action` from an agent with insufficient role → error; delegation
creates a card when `auto_card_on_delegation` is on. Golden: `ws_frames.json`.

**Effort.** ~2 days.

---

## 6.5 Real-time + integration · `◻ planned` · risk: med

**Goal.** Live board updates and integration with the existing fabric.

**Protocol (mirror ws.py ↔ protocol.ts, regenerate `ws_frames.json`).**
- client→hub `kanban_action` `{board_id, op, payload}` — agent mutations; counts
  against the token bucket (it writes). No actor field (anti-spoof).
- hub→observers `kanban_delta` `{board_id, op, card?/column?}` — broadcast to
  users who can see the board (owner + grantees + team), so the panel updates
  live (like `message`/`notification`). Reconciliation: a client applies the
  delta or, on version conflict, refetches `/full`.

**Integrations.**
- **Delegation → card** (opt-in): a 4.4 delegation drops a card in the landing
  column, `assignee` = delegate, `origin={kind:delegation}`; completion moves it
  to Done. **Escalation → card** (opt-in): a 4.3 escalation opens a card flagged
  needs-human.
- **Card ↔ thread:** a card's discussion is an Ampla conversation; comments link
  to `origin` so card chat and DM history stay coherent.
- **Inbox (Epic 02):** card assigned/moved-to-my-column → notification
  (`task_assigned`/`state_change`), reusing the existing notify pipeline.
- **Comment → notify (the "I need info" channel):** posting a comment notifies
  the card's `assignee` and the board owner (reason `participating`), and any
  `@mention` in the body notifies the mentioned agent's owner (reason `mention`),
  reusing `parse_mentions` and the Epic 02 pipeline. The commenter is never
  notified of their own comment; the recipient's `notify_level` and per-thread
  `ignored` subscription still gate it. This turns a card comment into a real
  request-for-information that reaches the right person without leaving the board.

**Security.** `kanban_delta` only to observers authorized for the board (no
cross-board/cross-user leak). Event-driven cards stay opt-in per board.

**Tests.** Hub integration: a move broadcasts a delta to an authorized observer
and not to an unauthorized one; delegation→card end-to-end (WS); notification on
assignment; **a comment notifies the assignee + owner; an `@mention` notifies the
mentioned agent's owner; the commenter is not notified of their own comment; a
muted/`ignored` thread suppresses it**. Golden: ws frames.

**Effort.** ~2 days.

---

## 6.6 Web UI · `◻ planned` · risk: low-med

**Goal.** A board view + a grants panel, all via `src/lib/api/` + `src/lib/ws/`
(components never `fetch` directly).

- `web/src/features/kanban/BoardPage.tsx`: columns + cards, live via the observer
  (`kanban_delta`). v1 uses explicit **move actions** (← →, "mover para…") with the
  anchor-based API; HTML5 drag-and-drop is a refinement on top of the same
  endpoint. Optimistic update + reconcile/rollback on 409.
- `BoardSettings.tsx`: visibility + **per-agent grants** (role chips), with the
  **danger-zone** confirm when granting `contributor`/`editor` to an agent.
- Card detail: Markdown body (sanitized) + comments thread.

**Tests.** vitest/RTL: renders columns/cards; a move calls the move API with the
right anchors + version; a 409 rolls back; grant panel shows the danger-zone for
agent write. A board snapshot.

**Effort.** ~2.5 days.

---

## 6.7 Deferred to v2 (noted, not built)

- **DAG dependencies + cycle detection** (agent-board): a card blocked until its
  deps are Done. Powerful for multi-agent pipelines; adds graph validation.
- **Quality gates** (`requires_review` blocks Done) and **auto-chaining**
  (`next_card`).
- **Live drag-and-drop** with cursor presence; column WIP visual warnings.
- **Live preset/linking** of boards across teams.

---

## Epic 06 milestone checklist

- [x] 6.1 Board/columns/cards/comments model + REST CRUD + authz + golden
  (`ab7f609`; foundation `2fd56c9`)
- [x] 6.2 Fractional-rank ordering + serialized-txn/optimistic-version concurrency
  + WIP-in-txn + rebalance — property + concurrency tests (`de4dbc0`)
- [x] 6.3 Per-agent per-board role grants (dev-only default) + audit; danger-zone
  confirm is the UI's job, deferred with the grants panel (`acd396d`)
- [x] 6.4 `amp_kanban_*` MCP tools + daemon `/kanban` + agent-key reads +
  `--strict-mcp-config` guarantee (`c69e93a`, `756500e`).
  ◻ opt-in event cards (delegation/escalation→card) deferred — see below
- [x] 6.5 `kanban_action`/`kanban_delta` WS frames + inbox notifications
  (comment/assignment/move) (`509312c`).
  ◻ delegation/escalation→card deferred — see below
- [x] 6.6 Board view (live + optimistic moves) — components only via api/ws
  (`fa758d2`). ◻ grants panel + danger-zone + card-detail/comments + drag-drop
  deferred to the dedicated UI pass
- [x] Every dangerous knob audited (agent write grant → `kanban_grant_set`)
- [x] All ordering/concurrency invariants covered by property + simulation tests

Recommended order: 6.1 → 6.2 (hardest; lock it down first) → 6.3 → 6.4 → 6.5 → 6.6.

### Deferred to a follow-up (not built; backend-ready)

- **Event-driven cards** (`auto_card_on_delegation`/`_escalation`): the hub-side
  `create_event_card` primitive exists (audited, `origin`-tagged), but routing an
  event to a *specific* board needs a board-selection rule (which board does a
  given delegation/escalation drop a card on?) that the spec doesn't pin down.
  Left out rather than shipping a speculative default; revisit with a board
  setting + an explicit resolution rule.
- **Grants/danger-zone UI panel**, **card detail + comments thread**, **HTML5
  drag-and-drop**: UI refinements on top of endpoints that already exist.

---

## Sources

- LexoRank (Jira ranking): https://tmcalm.nl/blog/lexorank-jira-ranking-system-explained/ ·
  https://support.atlassian.com/jira/kb/understanding-and-managing-lexorank-in-jira-server/
- Kanban position management & concurrency (pessimistic lock, unique constraint
  retry, rebalance): https://www.manukminasyan.com/blog/kanban-boards-position-management ·
  https://nickmccleery.com/posts/08-kanban-indexing/
- Fractional indexing: https://hollos.dev/blog/fractional-indexing-a-solution-to-sorting/
- Trello board permission roles (admin/member/observer):
  https://support.atlassian.com/trello/docs/configure-board-permissions/
- Prior art — MCP/agent boards: https://github.com/quentintou/agent-board ·
  https://github.com/Raman369AI/agent-kanban-pm · https://github.com/bradrisse/kanban-mcp ·
  https://github.com/tcarac/taskboard · https://github.com/eyalzh/kanban-mcp
