# Epic 02 — User Inbox (GitHub-style notifications)

A per-**user** triage inbox modeled on GitHub Notifications: a notification is a
**thread about a subject**, carries a **reason**, and moves through a triage
lifecycle (`unread` flag × `inbox|saved|done`). The operator processes it to
inbox-zero. Real-time deltas ride the existing observer WS.

> Why a user inbox (not an agent inbox): the daemon already has a per-agent local
> inbox (`bridge/.../message-store.ts`). This is different — it’s the **human
> operator’s** triage surface in the panel, aggregating everything that concerns
> *any of their agents* plus things addressed to them (approvals, escalations).

Research basis: GitHub thread object (`id, unread, reason, updated_at,
last_read_at, subject{title,url,type}, repository, subscription`), the read-vs-done
two-axis model, reasons enum, two-layer subscription (repo watch + thread
subscription), and filter qualifiers. We **copy the model and fix GitHub’s gaps**
(expose a real Saved mutation; deliver deltas over WS; materialize `unread`
server-side).

---

## Data model (hub) · new tables

New Alembic revision. Two tables + one settings table.

### `notifications`
| column | type | notes |
|---|---|---|
| `id` | int PK | |
| `user_id` | int FK→users.id, indexed | **owner of the inbox** |
| `subject_type` | str(16) | `dm \| mention \| task \| broadcast \| approval \| autorespond \| system` |
| `subject_key` | str(120), indexed | stable grouping key (e.g. `dm:backend-julio:mobile-eduardo`, `approval:<id>`, `thread:<root_id>`) |
| `agent_slug` | str(60), nullable, indexed | which of the user’s agents this concerns (the "repository" analog; null = account-level) |
| `reason` | str(24) | most-relevant current reason (enum below) |
| `title` | str(200) | short, **plain-text** summary (sanitized; agent-authored text is escaped) |
| `link` | str(255) | deep-link the panel resolves (e.g. `/?perspective=…&partner=…&msg=<id>`) |
| `actor` | str(120) | who/what triggered it (sender slug or "system") |
| `unread` | bool, default true | materialized; not computed by clients |
| `status` | str(8), default `inbox` | `inbox \| saved \| done` |
| `created_at` | UTCDateTime, indexed | |
| `updated_at` | UTCDateTime, indexed | bumped on new activity; drives sort |
| `last_read_at` | UTCDateTime, nullable | when the user last read it |

Indexes: `(user_id, status, updated_at)` for the inbox list;
`(user_id, subject_key)` unique-ish for collapsing (see grouping).

**Grouping.** New activity on the same `(user_id, subject_key)` **updates the
existing row** (bump `updated_at`, set `unread=true`, refresh `reason`/`title`)
instead of inserting — exactly GitHub’s "thread collapses events". `done` rows
**re-open** (→ `inbox`, `unread=true`) when a high-signal reason fires
(`mention`, `approval_requested`, `broadcast`); low-signal activity on a `done`
thread does not resurface it (configurable).

### `notification_subscriptions` (per-thread, fine-grained)
| column | type | notes |
|---|---|---|
| `id` | int PK | |
| `user_id` | int FK, indexed | |
| `subject_key` | str(120), indexed | |
| `state` | str(10) | `subscribed \| ignored` |
| `reason` | str(24), nullable | why subscribed |
| `created_at` | UTCDateTime | |

Unique `(user_id, subject_key)`. `ignored` mutes a thread even if the coarse
watch would deliver it; it **re-subscribes** automatically on a direct
`mention`/`approval_requested` (mute is safe).

### Notification preferences (coarse watch) — on `users` or a small table
Add to `users` (or a `notification_prefs` table if it grows):
- `notify_level` str(16) default `mentions_and_direct` — `all | mentions_and_direct | custom | mute` (the repo-watch analog, applied per owned agent via a JSON map if `custom`).
- `notify_email` bool default false (future; email isn’t wired — see §Out of scope).

### Reason enum (the agent-domain analog of GitHub’s `reason`)
`mention` · `direct_message` · `task_assigned` · `approval_requested` ·
`autorespond_completed` · `autorespond_blocked` · `broadcast` · `team_mention` ·
`participating` · `subscribed` · `state_change` · `security_alert` ·
`escalation` · `system`.

Stored as the **most-relevant current** reason (GitHub semantics): a thread that
was `participating` becomes `mention` when you’re @mentioned and stays there.

---

## Service & generation (hub)

New `NotificationService` (+ `NotificationRepository`), assembled in
`app/api/deps.py` like the others. Routes never touch the repo.

**Who creates notifications.** Notifications are a **side effect of existing
flows**, produced in the relevant service (not by clients):
- `message_service.send` / `send_broadcast`: when the recipient agent’s **owner**
  should know — DM to their agent (`direct_message`), an @mention parsed from the
  body (`mention`/`team_mention`), a `task` type (`task_assigned`), a broadcast
  (`broadcast`). Respect the recipient’s `notify_level` + per-thread subscription
  (mirror GitHub’s delivery gate: no subscription ⇒ no notification, except
  always-deliver reasons `mention`/`approval_requested`).
- Epic 03: `approval_requested`, `autorespond_completed`, `autorespond_blocked`,
  `security_alert`.
- Epic 04: `escalation`, `state_change`.

**Mentions.** `@slug` parsing of message bodies lands here (shared util used by
01’s mention rendering). Resolve `@slug` → owning user → notify that user with
reason `mention`. `@group` → `team_mention` for each member’s owner.

**Service methods.** `list(user, filter)`, `unread_count(user)`,
`mark_read(user, ids|all)`, `mark_unread(user, ids)`, `set_status(user, ids,
status)` (inbox/saved/done), `subscribe(user, subject_key, state)`,
`notify(...)` (internal, called by other services). All authz: a user only ever
sees/mutates **their own** notifications.

**Audit.** No new audit events needed (notifications are derived); but
`approval_*` and `security_alert` notifications correlate with existing audit
rows.

---

## REST surface (hub) — mirrors GitHub’s endpoint set

| method + path | purpose |
|---|---|
| `GET /api/notifications?filter=…&cursor=…` | list inbox; filter qualifiers below |
| `GET /api/notifications/unread-count` | badge count |
| `PATCH /api/notifications/{id}` | `{unread?, status?}` — mark read/unread, set inbox/saved/done |
| `POST /api/notifications/read-all` | mark all (optionally scoped by `agent`/`filter`) as read |
| `PUT /api/notifications/subscription` | `{subject_key, state}` — subscribe/ignore a thread |
| `GET /api/notifications/prefs` · `PATCH …/prefs` | coarse `notify_level` (+ per-agent map if custom) |

**Filter qualifiers** (parsed server-side into the query):
`is:unread|read|saved|done`, `reason:<reason>`, `agent:<slug>` (the `repo:`
analog — which owned agent), `from:<sender>`, `is:dm|mention|task|broadcast|approval`.
Built-in views map to canned filters: Inbox (`is:inbox`), Saved (`is:saved`),
Done (`is:done`), Approvals (`reason:approval_requested`), @Mentions
(`reason:mention`), Assigned (`reason:task_assigned`).

All new endpoints → regenerate `openapi.json` golden.

---

## Real-time (WS) — deliver deltas, not polling

New hub→client frames (the inbox rides the **observer** connection the panel
already opens):
- `NotificationFrame {type:"notification", notification: NotificationOut}` — a new
  or updated (collapsed) notification for this user.
- `NotificationReadFrame {type:"notification_read", ids: list[int] | "all",
  unread_count: int}` — read-state changed elsewhere (multi-tab/device sync).

The observer WS authenticates by the same session cookie and already knows the
user; the hub pushes only that user’s notifications. Add both frames to `ws.py`
+ `protocol.ts` + `ws_frames.json` (bridge mirror green even though the daemon
doesn’t use them — the panel does; the mirror test just validates shapes).

---

## Web (panel)

- New feature `web/src/features/inbox/`: `InboxPage`, `NotificationRow` (reason
  **chip**, agent folder, actor, relative time, unread bold), left rail with
  built-in views + saved filters + grouping by agent, bulk multi-select +
  triage actions (Read / Saved / Done / Unsubscribe), keyboard triage
  (`E`=done, `Shift+I`=read, `Shift+U`=unread, `Shift+M`=unsubscribe).
- New `web/src/lib/api/notifications.ts` (`notificationsApi`) + a Zustand
  `inbox` store (`items`, `unreadCount`, filters, optimistic triage).
- `observer.ts` gains `onNotification` / `onNotificationRead` handlers → store.
- **Topbar:** an inbox bell with an unread **badge** next to the account avatar;
  clicking opens `/inbox`. (Sits in `AppShell`/`AccountMenu` area.)
- Read ≠ done is preserved in the UI: skimming marks read but never archives an
  approval.

## Security

- `title`/`actor` come partly from agent-authored content → **store and render
  as plain text** (escape; no markdown/HTML in notification rows). The deep-link
  `link` is constructed by the hub from validated ids, never from agent text.
- Strict per-user authorization on every read/mutate (a user cannot touch
  another user’s notifications or enumerate ids — 404 on cross-user id).
- Delivery gate prevents notification spam: respect `notify_level` + per-thread
  `ignored`; always-deliver only `mention`/`approval_requested`/`security_alert`.
  Add a per-user generation rate cap so a flood of messages can’t explode the
  table (collapse + cap).
- Retention: a periodic prune of `done` notifications older than N months
  (GitHub keeps ~5) — config `AMP_NOTIFICATION_DONE_TTL_DAYS`.

## Tests

- **Unit (service, fake repo):** collapsing (second event on same `subject_key`
  updates, not inserts); reason precedence (participating→mention sticks);
  `done` re-opens on `mention` but not on low-signal; delivery gate honors
  `notify_level`/`ignored`; mark-all-read; cross-user isolation.
- **Integration (TestClient):** the 6 endpoints incl. filter parsing; sending a
  DM/mention/broadcast generates the right notification for the right user; WS
  observer receives `notification`/`notification_read`.
- **Golden:** `openapi.json` (new endpoints) + `ws_frames.json` (two frames).
- **Property:** the filter-qualifier parser (round-trip / never crashes on junk);
  the mention parser (every `@slug` in any context resolves or is ignored, never
  injects).
- **Web:** inbox store triage (optimistic + reconcile), `NotificationRow`
  snapshot, keyboard triage, badge count.

## Out of scope (v1)

- Email/push delivery (no SMTP in a 100% local system — keep `notify_email` as a
  schema stub; a future epic can add a webhook/desktop-push channel).
- Saved custom filters persistence can be v1.1 (ship built-in views first).

## Effort

Largest epic: ~4–6 days (new tables + service + 6 endpoints + 2 WS frames +
full inbox UI). Can ship in slices: (a) model + generation on `dm`/`mention` +
list/read endpoints + minimal UI; (b) saved/done triage + WS deltas + badge;
(c) subscriptions + filters + bulk/keyboard.

## Milestone checklist

Slice (a) shipped in `50ca97d` (foundation). Slice (b) shipped in `15b470f`
(WS deltas). Slice (c) shipped across `f14c0fb` (read-all), `0485856`
(prefs+gate), `b22971f` (reason views), `981ed37` (subscriptions), `a53860c`
(rate cap + retention), `26883a8` (filter parser), `878c650` (search box),
`81c0c12` (bulk + keyboard). **Epic 02 complete.**

- [x] Tables + migration + `NotificationService`/repo
- [x] Generation hooks in `message_service` (dm/mention/task/broadcast)
- [x] REST endpoints + openapi golden — list, unread-count, PATCH, read-all,
  prefs (GET/PATCH), subscription (PUT) all shipped
- [x] WS frames + ws_frames golden + observer handlers — `notification` +
  `notification_read`, pushed per-user; live badge + list
- [x] Inbox UI (rows, views, triage) + topbar bell/badge + delivery-level
  selector + canned reason views + per-thread "Ignorar" + search box (`?q=`)
  + bulk multi-select + keyboard triage (E/⇧I/⇧U/⇧M)
- [x] Subscriptions (`subscribe`/`ignore`, safe-mute) + prefs (`notify_level`)
  + delivery gate + canned reason views — shipped
- [x] Filter-qualifier parser (`is:`/`reason:`/`agent:`/`from:`) server-side
  + `?q=` + property test + web search box
- [x] Retention prune (startup) + per-user generation rate cap — shipped
  (`AMP_NOTIFICATION_DONE_TTL_DAYS` / `AMP_NOTIFICATION_MAX_NEW_PER_HOUR`)
