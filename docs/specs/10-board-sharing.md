# Epic 10 — Board Sharing (per-user membership + member-owned agent grants)

> **Status: planned, not built.** Captured mid-discussion (the design below is
> settled) so it survives a context compaction. Requested by the maintainer:
> *"quero compartilhar um quadro com pessoas específicas, e cada pessoa com
> acesso também pode plugar os próprios agentes."*

## Problem

Today a kanban board's **human** access is all-or-nothing:

```python
# hub/app/services/kanban_service.py
def _human_can_see(self, user, board) -> bool:
    return user.role == "admin" or board.owner_id == user.id or board.visibility == "team"
```

- `team` → every teammate; `private` → owner + admin only.
- The grant system (`kanban_agent_grants`) is **agents only** (model docstring:
  *"Restricts AGENTS only — human members keep full edit"*).

So there is **no way to share a private board with a specific person**, and
therefore no way for that person to bring their own agents onto it.

## Goal

1. A **private** board can be shared with **specific users** (not just all-team).
2. A user with access (owner, member, or team) can **grant their own agents** a
   role on the board — but only their own; the owner can still grant anyone.

## Design (settled)

### Data model
New table `kanban_board_members` (one Alembic revision; new table, no backfill):

| column | type | notes |
|---|---|---|
| `id` | int PK | |
| `board_id` | int FK→kanban_boards.id | indexed |
| `user_id` | int FK→users.id | the shared-with person |
| unique `(board_id, user_id)` | | |

### Authorization changes (`KanbanService`)
- **Human visibility** — `_visible_board` also passes when the user is a member:
  `admin OR owner OR visibility=="team" OR is_member(board, user)`. (`_human_can_see`
  stays sync for the cheap cases; the membership check is an async repo call in
  `_visible_board`.) A member gets the same human edit rights a team member has
  (create/move/edit cards) — governance stays owner-only.
- **Member management** (`add_member` / `remove_member` / `list_members`) —
  **owner/admin only** (`_owned_board`). Validates the target user exists
  (UserRepository). Audited: `kanban_member_added` / `kanban_member_removed`.
- **Agent grants — relaxed authority** (the headline of this epic). `set_grant` /
  `remove_grant` today are owner/admin only; change to:
  - owner/admin → grant/revoke **any** agent (unchanged);
  - else, a user who **can see the board** AND **owns the agent**
    (`agent.user_id == user.id`) → may grant/revoke **that** agent only;
  - otherwise 403.
  `list_grants` → allow any board-visible user to read (so members can manage
  their own). Keep `kanban_grant_set` / `kanban_grant_removed` audits.

### REST
- `GET /api/kanban/boards/{id}/members` (board-visible read), `POST` (owner/admin,
  body `{user_id}`), `DELETE /api/kanban/boards/{id}/members/{user_id}` (owner/admin).
- Grant routes (`PUT/DELETE/GET .../grants`) keep their paths; only the service
  authz changes.
- Member picker source: `GET /api/users` already exists and is **not**
  admin-gated (`list_users` uses `get_current_user` + `auth.list_users(user)`),
  so the owner can list teammates to add. The member's own agents for the grant
  picker come from `agent_repo.list_by_user` (the panel already lists "my agents").

### Web (`BoardSettings.tsx` + `BoardPage.tsx`)
- New **"Membros do quadro"** section (owner/admin only): list members + add (pick
  a team user from `usersApi`) + remove. Most useful when visibility = `private`.
- Make the **"Permissões"** button + the **agent-grants** section reachable by a
  **member** (not just `canManage`): a member sees only the grant sub-panel, and
  the agent picker is limited to **their own** agents; they can revoke only their
  own agents' grants. Owner/admin keep the full panel (visibility, default role,
  members, all grants, danger-zone). Pass `user` + `isOwner`/`isMember` into
  `BoardSettings` (today gated entirely by `canManage = owner||admin`).

### Tests
- Service unit: a member can see a private board; a non-member can't (404); member
  management is owner-only; **a member grants their OWN agent (ok) but not another
  user's agent (403)**; owner grants any; revoke symmetry; cross-board isolation.
- Integration: REST members CRUD + the cross-user 403/404 convention; golden
  `openapi.json` (members routes + any schema).
- Web: members section (owner) + the member-limited grant panel.

## Flow it enables
1. Owner sets the board **Privado**.
2. Owner adds **João** as a member → João now sees/edits the board.
3. João grants **his own agent** `joao-backend` (Colaborador) → that agent can act
   on the board. João cannot grant someone else's agent; only the owner can.

## Build order
model + migration → repo → service authz (membership + relaxed grants) → routes →
web (members section + member grant panel) → tests + golden. Backend-first, green
commit per slice, like Epics 06–09.

## Sources
- Builds on Epic 06 grants ([`06-kanban.md`](06-kanban.md)) and the human/agent
  authorization split in `kanban_service.py`.
