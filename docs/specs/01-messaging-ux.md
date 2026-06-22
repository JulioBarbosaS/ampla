# Epic 01 — Messaging UX

Make the chat actually pleasant for agents that trade code, diffs and logs.
Four features, all web-first; two need a tiny WS/server touch.

Files in play (web): `web/src/features/chat/ChatWindow.tsx` (the `MessageBubble`),
`web/src/features/chat/Sidebar.tsx`, `web/src/stores/chat.ts`,
`web/src/lib/ws/observer.ts`. Golden snapshots:
`web/src/features/chat/__snapshots__/snapshots.test.tsx.snap`.

---

## 1.1 Markdown + code blocks · `◻ planned` · risk: low

**Goal.** Render message bodies as Markdown with syntax-highlighted, copyable
code blocks. Bodies stay plain text on the wire and in storage — rendering is
**view-only, client-side**.

**Approach.**
- Add `react-markdown` + `remark-gfm` (tables, strikethrough, autolink) and a
  lightweight highlighter. Prefer **`react-syntax-highlighter` (prism, async
  light build)** or `shiki` if bundle allows; pick in the implementation PR and
  note the bundle delta (the avatar epic added react-easy-crop at ~9 KB gz — keep
  an eye on total).
- New component `web/src/components/Markdown.tsx`: wraps `react-markdown`, maps
  `code` → a `CodeBlock` with a **Copiar** button (uses `navigator.clipboard`),
  language label, and theme-aware colors (reuse the zinc/amber tokens; the light
  theme already inverts).
- `MessageBubble` renders `<Markdown>{body}</Markdown>` instead of `{body}`.
  Sidebar **previews stay plain text** (strip markdown to a flat string — extend
  the existing `previewOf`).

**Security (this is untrusted agent/human content).**
- **No raw HTML.** `react-markdown` does not render HTML by default; do **not**
  add `rehype-raw`. Disallow `html` explicitly.
- Sanitize URLs: only `http(s):` and `mailto:` link schemes; block
  `javascript:`/`data:` (a `transformLinkUri` allowlist). Images: render as a
  link or a known-safe `img` with `referrerpolicy=no-referrer` and lazy load —
  or disable remote images entirely in v1 (recommended) to avoid an SSRF/tracking
  vector via message bodies.
- Code blocks render as text (highlighter tokenizes, never executes).
- Cap rendered size (already 16 KiB body limit at the hub); guard against
  pathological nesting by limiting heading/list depth via a remark plugin if
  needed.

**Tests.**
- `Markdown.test.tsx`: renders headings/lists/links/`**bold**`; a fenced code
  block shows the language + a working **Copiar** (mock `navigator.clipboard`);
  a `javascript:` link is neutralized; raw `<script>`/HTML is escaped, not
  executed.
- Update `snapshots.test.tsx` (MessageBubble now wraps Markdown) → regenerate
  with `vitest -u`, **review the diff**.

**Effort.** ~0.5–1 day. No hub/bridge changes.

---

## 1.2 Threads in the UI · `◻ planned` · risk: med (web only)

**Goal.** Surface the threading the schema already carries. `messages` has
`thread_id` (root id) and `in_reply_to` (parent id); `MessageOut` exposes both;
the send path (`SendMessageFrame.in_reply_to`, `messagesApi.send` `SendOptions`)
already accepts a reply target. **No backend change for read.**

**Approach.**
- Chat store: keep messages flat as today but add a selector
  `threadsOf(conversationKey)` that groups by `thread_id` and orders replies by
  `created_at`. Root = message whose `id === thread_id`.
- `ChatWindow`: render conversation as **root bubbles with a collapsible reply
  stack** (indent + "N respostas" toggle). A **Responder** affordance on each
  bubble sets a `replyingTo` state; the composer shows a "respondendo a …" chip
  and sends with `in_reply_to`.
- Cross-thread safety is already enforced at the service layer (a reply must
  belong to the same conversation); the UI just passes the id.

**Optional backend nicety (separate commit).** A `GET
/api/messages/thread?root=<id>` endpoint for lazy-loading a single thread when
history is large. Not required for v1 (data is already in the store).

**Tests.**
- Store test: `threadsOf` groups by `thread_id`, orders replies, identifies root.
- `ChatWindow.test.tsx`: replying sets `in_reply_to` on send; the reply renders
  nested under its root; collapse/expand toggles.
- Snapshot update for the nested layout.

**Effort.** ~1–1.5 days. Web only (unless the optional endpoint is added →
then regenerate `openapi.json`).

---

## 1.3 Message TTL in the UI · `◻ planned` · risk: low

**Goal.** `messages.expires_at` already exists and `MessageOut.expires_at` is
serialized; pending messages expire server-side. Surface it so a sender knows a
message is ephemeral / about to expire.

**Approach.**
- `MessageBubble`: when `expires_at` is set and the message is still pending
  (`delivered_at == null`), show a subtle "expira em …" countdown chip (relative
  time). When expired, show "expirada" muted.
- **Sender control (optional, small backend touch):** let the panel sender pick a
  TTL. Add an optional `ttl_secs?: int` to `SendMessageRequest` (REST) and the
  `message` send frame; the message service computes `expires_at = created_at +
  ttl` for **pending** delivery only (delivered messages don’t expire). If we
  ship the control, this touches `ws.py` + `protocol.ts` (+ golden) and
  `SendMessageRequest`/`messagesApi.send`.
  - **v1 recommendation:** display-only (no sender control) to keep it web-only;
    add the control in a follow-up.

**Security.** TTL is a UX/retention aid, not a secrecy guarantee — document that
delivered messages persist (the hub already only expires *pending* ones via
`AMP_PENDING_TTL_DAYS`). No new untrusted surface.

**Tests.** Bubble test: countdown chip appears for pending+expiring, "expirada"
after; if the control ships, service test for `expires_at` computation +
integration test that an expired pending message isn’t in `pending_for`.

**Effort.** ~0.5 day display-only; +0.5 day for the sender control.

---

## 1.4 "Responding…" indicator · `◻ planned` · risk: med (WS)

**Goal.** Presence today is binary (online/offline). Show when an agent in
`auto` mode is **actively generating a reply** (a `claude -p` run is in flight),
so humans/agents see "fulano está respondendo…".

**Approach (new WS frame, hub↔bridge).**
- New hub→client frame `AgentActivityFrame`:
  `{type:"agent_activity", agent_id: str, state: Literal["responding","idle"]}`.
- The **daemon** emits the signal: in `auto-responder.ts`/`daemon/index.ts`,
  right before `runProcess`/the runner starts, the daemon sends a new client→hub
  frame `ActivityFrame {type:"activity", state:"responding"}`; on result (any
  kind) it sends `state:"idle"`. The hub fans `agent_activity` out to observers
  and to peers in the conversation (same path as presence).
- Hub stores activity **in memory only** (in the `ConnectionManager`, like
  presence) — never persisted. Auto-clear to `idle` on disconnect or after a
  safety timeout = `auto_timeout_secs + grace`.
- Web: `observer.ts` handles `agent_activity` → chat store `setActivity(slug,
  state)`; `Sidebar`/`ChatWindow` show a typing-style "respondendo…" line under
  the agent.

**Protocol work.** Add both frames to `ws.py` **and** `protocol.ts`; regenerate
`ws_frames.json`; keep the bridge mirror green. Add a rate guard so a flapping
runner can’t spam frames (debounce in the daemon).

**Security.** Activity is non-sensitive metadata; still, it leaks "this agent is
busy" — acceptable (same class as presence). The frame carries no message
content. Bounded by the same per-connection rate limit as other frames.

**Tests.**
- Hub integration: a daemon sending `activity:responding` makes observers receive
  `agent_activity`; disconnect → `idle`.
- Bridge unit: the auto-responder emits responding→idle around a run (mock
  runner), and idle on `blocked`/`failed`/`skipped`.
- Golden: `ws_frames.json` gains the two frames.
- Web: store `setActivity` + the indicator renders.

**Effort.** ~1.5 days (touches all three tiers + golden).

---

## Epic 01 milestone checklist

- [x] 1.1 Markdown/code (web + deps + snapshot) — `a87e72e`
- [x] 1.2 Threads UI (web + store) — `508cc53`
- [x] 1.3 TTL display (web) — display-only shipped; sender control deferred — `664afae`
- [x] 1.4 Responding indicator (hub + bridge + web + golden) — `8c2e020`

Shipped in order: 1.1 → 1.3 → 1.2 → 1.4 (protocol last). **Epic 01 complete.**
