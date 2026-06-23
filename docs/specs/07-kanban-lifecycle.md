# Epic 07 — Kanban Lifecycle & Origin Linking

> From the project-suggestions list · **item #10** ("fechar o ciclo kanban").

The natural completion of Epic 06. Today a board can grow **event cards** —
a delegation or an escalation can drop a card in a landing column (opt-in per
board) — but the card then goes stale: nothing moves it to **Done** when the
underlying work finishes, and the `origin` that ties a card back to the
conversation/delegation that spawned it is stored but **never surfaced** in the
UI. This epic closes that loop in both directions:

- **Lifecycle:** a completed delegation (and a resolved escalation) **auto-moves
  its card to a Done column**, audited and broadcast like any other move.
- **Origin linking:** a card created from a delegation/escalation/message
  **deep-links back** to that conversation, and a conversation can be **turned
  into a card** — filling the `message|thread` origin kinds that the data model
  already reserves but no code sets yet.

Files in play: `hub/app/services/kanban_service.py`,
`hub/app/services/message_service.py`, `hub/app/services/delegation_service.py`,
`hub/app/services/autorespond_service.py`, `hub/app/repositories/kanban_repo.py`,
`hub/app/api/routes/kanban.py`, `hub/app/schemas/kanban.py`,
`hub/app/models/kanban.py`, `hub/app/schemas/ws.py`,
`bridge/src/shared/protocol.ts`, `web/src/features/kanban/*`,
`web/src/features/chat/*`, `web/src/lib/api/*`.

> Builds on: Epic 06 (boards/cards, `is_done` columns, `kanban_delta`, the
> `create_card_for_event` primitive, the `origin` JSON column), Epic 04
> (delegation + escalation), Epic 02 (Inbox notifications), and the message/
> conversation model (threads via `thread_id`).

## Current state (what exists vs. what's missing)

**Exists (Epic 06 left these backend-ready):**

- `KanbanService.create_card_for_event(*, owner_id, flag, title, body, assignee,
  origin, priority)` (`kanban_service.py:663`) → routes to
  `first_board_with_flag(owner_id, flag)` and calls
  `create_event_card(board_id, data, *, origin, audit_actor="system")`
  (`kanban_service.py:686`), which writes `origin` onto the card and audits it.
- Board flags `auto_card_on_delegation` / `auto_card_on_escalation` (`DELEGATION_FLAG`
  / `ESCALATION_FLAG`, `kanban_service.py:660`).
- `KanbanCard.origin: dict | null` (`models/kanban.py:70`), surfaced as
  `CardOut.origin` (`schemas/kanban.py:137`). Set today only as
  `{"kind":"delegation","id":<delegation_id>}` (`delegation_service.py:134`) and
  `{"kind":"escalation","from":<sender>}` (`autorespond_service.py:145`).
- `KanbanColumn.is_done: bool` (`models/kanban.py:50`); a board is seeded with a
  `"Concluído"` column `is_done=True`; a board may have several done columns.
- Delegation model with `status: open|completed|declined`, `root_message_id`,
  `result_message_id` (`models/delegation.py:10`). Completion is detected in
  `MessageService._maybe_complete_delegation()` (sets `status="completed"`,
  `result_message_id`, notifies the delegator) via
  `DelegationRepository.find_open_for_reply(...)`.
- Conversation history: `GET /api/messages/conversation?a=&b=&limit=`; the panel
  already deep-links with `/?perspective=<a>&partner=<b>&msg=<id>`
  (`autorespond_service.py:113`).

**Missing (this epic builds it):**

1. **No hook moves a card to Done when its delegation completes** — the card is
   created on delegation *open* and then orphaned.
2. **Escalation has no "resolved" state** — it's a one-shot notification
   (`AutorespondRun` + `Notification reason="escalation"`); there's nothing to
   key a card-close off of.
3. **`origin.kind` `"message"` / `"thread"` are reserved but never set** — no way
   to turn a conversation into a card.
4. **`origin` is never surfaced in the UI** — no back-link from a card to its
   source conversation, and no way to look a card up by its origin.

---

## 7.1 Card lookup by origin + the lifecycle move primitive · `◻ planned` · risk: med

**Goal.** The shared mechanism the rest of the epic stands on: find the card a
given event produced, and move it to a Done column **as the system**, audited and
broadcast — without an authenticated human actor in the request.

**Model.** No new columns. Add a lookup + a system-move on the service/repo:

- `KanbanRepository.card_by_origin(kind: str, ref) -> KanbanCard | None` — matches
  on the JSON `origin` (`kind` + the kind's identity key: `id` for delegation,
  `from`+owner board for escalation, `id` for message/thread). Indexed read; the
  `origin` JSON is small and per-owner-board, so a scan within the owner's boards
  is acceptable, but prefer a generated/expression index on `origin->>'kind'` +
  `origin->>'id'` if the dialect supports it (SQLite: a partial index on the
  extracted columns, or a denormalized `origin_kind`/`origin_ref` pair — **decision
  point**, see Security/Tests).
- `KanbanService.complete_card_for_event(*, kind, ref, audit_actor="system") ->
  KanbanCard | None` — looks the card up, resolves the board's **target done
  column** (the leftmost `is_done` column, or a board-configured one — see 7.4),
  and moves it there reusing the existing `_move` core (so ranking, `version`
  bump, `kanban_delta` broadcast and audit all happen exactly as a human move
  would). No-op (returns `None`) if there's no card, it's already in a done column,
  or the board opted out.

**The done-gate question.** A normal move into a done column is blocked when the
card `_is_blocked` (`kanban_service.py:372`, unmet dependencies). A *lifecycle*
move is the system asserting the work is done — **decision:** the lifecycle move
**still respects** the dependency gate (a card with open deps can't be auto-Done);
if blocked, it instead lands in the column **before** the done column (or stays
put) and records an audit note, so the invariant "Done ⇒ deps Done" never breaks.

**Security.** `audit_actor="system"`; the move is a hub-side side effect of a
*trusted* event (a delegation the hub itself recorded completing), never
client-driven — same trust basis as `create_card_for_event`. Every lifecycle move
audits (`kanban_event_card_done` with `{card_id, origin, trigger}`). The
`kanban_delta` only reaches observers already authorized for that board.

**Tests.** Unit: `card_by_origin` matches the right card and ignores other kinds/
owners; `complete_card_for_event` moves to the done column, is idempotent
(second call is a no-op), respects the dep-gate (blocked card not auto-Done),
broadcasts a delta, audits. Integration: end-to-end move visible on `/full`.

**Effort.** ~1.5 days.

---

## 7.2 Delegation completion → card to Done · `◻ planned` · risk: low-med

**Goal.** When a delegation is marked `completed`, its card moves to Done
automatically.

**Wiring.** `MessageService._maybe_complete_delegation()` is the single place a
delegation flips to `completed`. After it commits the status change, call
`KanbanService.complete_card_for_event(kind="delegation", ref=delegation.id)`
(best-effort, mirroring how `delegation_service` calls `create_card_for_event` on
open — a kanban failure never blocks the message path). Gated by the same board
opt-in that created the card (`auto_card_on_delegation`): a board that didn't
auto-create the card won't auto-close one. A `declined` delegation optionally
moves the card to a board-configured "blocked/declined" landing instead of Done
(**decision:** v1 just leaves it and notifies; auto-routing declines is a 7.4
refinement).

**Security.** Completion is already authenticated (it's the delegate's reply,
attributed to the authenticated socket); the kanban side-effect runs as `system`.
No new external surface.

**Tests.** Hub integration: open a delegation on a board with the flag on (card
created in landing) → the delegate replies → the card is now in the Done column,
a `kanban_delta` was broadcast, an audit row exists; with the flag off, no card and
no move; a delegation whose card a human already moved/deleted is a clean no-op.

**Effort.** ~1 day.

---

## 7.3 Escalation resolution → card to Done · `◻ planned` · risk: med

**Goal.** Give an escalation a notion of "resolved" so its card can close — today
it has none.

**Design (the card is the source of truth).** Rather than add an escalation state
table, treat the **escalation card itself** as the resolution surface:

- The escalation card already lands assigned to the owner, `priority=high`,
  `origin={"kind":"escalation","from":<sender>}`. When a **human moves that card
  into a Done column** (a normal authorized move), the hub recognizes an escalation
  card reaching Done and **resolves the escalation**: it records an audit
  (`escalation_resolved` with the `from`/owner) and, optionally, notifies the
  agent's owner-loop that the human handled it. No auto-move is needed here — the
  human's move *is* the resolution; this slice is about giving that move *meaning*.
- **Convenience auto-resolve (opt-in):** when the owner **replies in the escalated
  conversation** (`GET conversation a=<agent>,b=<sender>`), the hub matches an open
  escalation card by origin (`from=<sender>` on one of the owner's boards) and
  moves it to Done via 7.1. This closes the loop without the owner touching the
  board. Gated by a board flag `auto_done_on_escalation_reply` (default off, since
  it watches the message stream).

Because escalations have no row of their own, "open vs. resolved" is derived from
the card's column (`is_done` ⇒ resolved). That keeps the model honest: the board
*is* the state.

**Security.** Auto-resolve only fires for the **owner's own reply** to the escalated
sender (authenticated), on a board the owner controls — never on agent traffic.
Opt-in per board. Audited.

**Tests.** Hub integration: moving an escalation card to Done records
`escalation_resolved`; with `auto_done_on_escalation_reply` on, the owner replying
to the sender moves the matching card to Done; an unrelated reply does nothing; a
non-owner can't trigger it.

**Effort.** ~1.5 days.

---

## 7.4 Origin surfacing — card ↔ conversation, both ways · `◻ planned` · risk: med

**Goal.** Make `origin` *useful*: open the source conversation from a card, and
turn a conversation/thread into a card (filling the `message`/`thread` kinds).

**Resolver endpoint.** `GET /api/kanban/cards/{id}/origin` →
`{kind, label, deep_link, available}` where the hub resolves the raw `origin`
into a panel target:
- `delegation` → look up the delegation, return `from`/`to`/`root_message_id` and a
  `deep_link` (`/?perspective=<from>&partner=<to>&msg=<root_message_id>`).
- `escalation` → `from`/owner-agent and a conversation deep-link.
- `message`/`thread` → the message/thread id and its conversation deep-link.
- `available:false` if the source was deleted/expired (cards outlive messages with
  a TTL) — the UI shows "origem indisponível" rather than a dead link.

Resolution lives in `KanbanService` (routes never touch repos); the link strings
reuse the panel's existing deep-link convention.

**Conversation → card (closing `message`/`thread`).** A new affordance in the chat
(`web/src/features/chat/*`) — "criar card desta conversa" — calls
`POST /api/kanban/boards/{id}/cards` with `origin={"kind":"thread","id":<thread_id>}`
(or `message`). This is a normal authenticated human card-create (per Epic 06
authz), so no new trust surface; it just sets the previously-unused origin kinds.
The card then deep-links back via the resolver — the loop is symmetric.

**Web.** `CardDetail.tsx` gains an **"Origem"** row: an icon/label
("Delegação de X", "Escalação de Y", "Conversa") that links to the deep target
(or shows unavailable). The chat gets the "criar card" action with a board/column
picker (reusing `kanbanApi`). Per the standing rule, the panel now exposes the
`origin` the backend has carried since Epic 06.

**Security.** The resolver returns a link only for boards/conversations the caller
can already see (authz on both the card and the resolved conversation); it never
leaks a conversation the viewer isn't a party to. Origin bodies are not rendered
here — only ids/labels/links.

**Tests.** Hub: resolver returns the right deep-link per kind, `available:false`
for a deleted source, 403/404 across users; creating a card from a thread sets
`origin.kind="thread"`. Web (vitest/RTL): `CardDetail` renders the Origem link and
the unavailable state; the chat "criar card" action calls the API with the thread
origin. Golden `openapi.json` for the new endpoint.

**Effort.** ~2 days.

---

## Deferred to a follow-up (noted, not built)

- **Auto-chaining** (`next_card`): completing a card spawns the next in a defined
  pipeline — powerful with delegation, but needs a pipeline model (Epic 06 §6.7).
- **Routing declines/failures** to a board-configured column (7.2 leaves declines
  in place); needs a per-board "decline lands here" setting.
- **Bi-directional live presence** on the card (who's viewing) — UI polish.

---

## Epic 07 milestone checklist

- [ ] 7.1 `card_by_origin` + `complete_card_for_event` (system move, dep-gate
  respected, audited, delta) — unit + integration
- [ ] 7.2 Delegation completion → card to Done (best-effort hook in
  `_maybe_complete_delegation`, gated by `auto_card_on_delegation`)
- [ ] 7.3 Escalation resolution (card-to-Done = resolved + opt-in auto-resolve on
  owner reply) — audited
- [ ] 7.4 Origin resolver endpoint + conversation→card action + `CardDetail`
  "Origem" link — fills `message`/`thread` kinds; golden openapi; web tests
- [ ] Every lifecycle move audited (`kanban_event_card_done` /
  `escalation_resolved`); no Done ⇒ deps-Done invariant broken
- [ ] UI exposes `origin` (standing "UI covers backend" rule)

Recommended order: 7.1 (the primitive) → 7.2 (cheapest, highest value) → 7.4
(surfacing) → 7.3 (escalation, the fuzziest).

---

## Sources

- Epic 06 spec (origin, `is_done`, `create_card_for_event`): [`06-kanban.md`](06-kanban.md)
- Epic 04 delegation/escalation: [`04-agent-policy.md`](04-agent-policy.md)
- Trello "convert to card" / linked cards (UX precedent for origin linking):
  https://support.atlassian.com/trello/docs/linking-cards/
