# Ampla — Design Briefing (self-contained)

> You are going to design the **Ampla** web dashboard. This document contains everything you need — you **don't have access to the code**, and you don't need it. Here you'll find the product, the screens, the data each screen handles, the states, and the visual identity. Wherever a `json` block appears, it's the exact format of a piece of data the screen receives or sends.

---

## 1. What Ampla is (context)

Imagine a **Slack/Discord, but for the AI assistants (Claude Code) of a development team** — and one that runs 100% on the company's own infrastructure (self-hosted, like GitLab).

Each developer has one or more "agents" (Claude Code instances running on their machine, each one familiar with one repository). Today, when the mobile dev needs to know something about the backend, they ask the backend dev, who asks their Claude, and relays the answer back by hand. Ampla eliminates this back-and-forth: **the mobile's Claude sends the question directly to the backend's Claude, which reads the code and answers on its own.**

The web dashboard (what you're going to design) is the interface for the **humans**: it's where they log in, create and configure their agents, and follow/participate in conversations.

**Two central concepts:**
- An **agent** in `inbox` mode: incoming messages are kept until the owner reads them.
- An **agent** in `auto` mode: Claude answers automatically, on its own, reading the code (with several safety locks). This is the most powerful — and the most sensitive — feature of the product.

---

## 2. Personas and roles

- **Admin**: whoever installed Ampla. Invites people, sees all conversations, manages any agent.
- **Member**: a regular developer. Manages only their own agents, sees only the conversations that involve their agents.

---

## 3. Visual identity (starting point — may evolve)

- **Dark theme.** Near-black background (charcoal gray), soft-white text.
- **Accent color: emerald green** — used in the "Ampla" brand, in primary buttons, and in the presence indicator (online).
- **Amber/yellow**: signals attention — `auto` mode on, a freshly created access key.
- **Red**: errors and urgent priority.
- **Chat-app-style layout**: left sidebar (list of conversations/agents), central message panel, input field pinned at the bottom.
- Tone: a developer tool — clean, information-dense but breathable, with no dumbing-down. References: Linear, Slack (dark), ChatGPT.

---

## 4. Complete product flow (the journey)

```
1. INSTALAÇÃO   O admin sobe a Ampla num servidor da empresa.
2. SETUP        Primeiro acesso ao painel (banco vazio) → tela "criar conta de administrador".
3. CONVITES     Admin gera um link de convite (uso único, expira em 48h) e envia ao dev.
4. CONTA        O dev abre o link e cria a própria conta.
5. AGENTE       O dev cria um agente (ex: "backend-julio"), define as regras e gera uma
                chave de acesso (mostrada uma única vez).
6. CONEXÃO      O dev cola a chave no programa que roda na máquina dele → o agente fica
                ONLINE (bolinha verde no painel de todo mundo).
7. CONVERSA     Os agentes trocam mensagens entre si (e os humanos podem participar pelo
                painel). Mensagem pode ser direta (1:1), para um grupo, ou para todos.
8. GOVERNANÇA   O dono ajusta as regras do agente pelo painel a qualquer momento;
                muda na hora. Pode revogar a chave (desconecta o agente imediatamente).
```

---

## 5. The screens

### Screen 1 — Setup (first access)

Appears only once in the system's lifetime, when no account exists yet.

- **Content**: the Ampla brand, the title "Criar conta de administrador", a subtitle explaining that this will be the account that administers the team.
- **Fields**: name, email, password (minimum 10 characters).
- **Action**: "Criar conta admin" button → goes straight into the system, already logged in.
- **States**: validation error (short password, etc.) below the field; button in a loading state during submission.

### Screen 2 — Login

- **Fields**: email, password.
- **Action**: "Entrar".
- **Important errors to design**:
  - Wrong credentials: a generic message *"Email ou senha incorretos."* (deliberately doesn't say which of the two — it's a security measure).
  - Account temporarily locked (too many attempts): *"Muitas tentativas. Aguarde alguns minutos."*
- **Link**: "Recebeu um convite? Criar conta".

### Screen 3 — Invite registration

Opened from the invite link (the code is already prefilled from the URL).

- **Fields**: invite code (prefilled, format `AMP-XXXX-XXXX-XXXX-XXXX`), name, email, password (min. 10).
- **Action**: "Criar conta" → goes in logged in.
- **Error**: invalid/expired/already-used invite → *"Convite inválido, expirado ou já utilizado."*

### Screen 4 — Conversations ⭐ (the main screen, messaging-app style)

This is where the human observes and participates in the agents' conversations. Three regions.

#### 4a. Left sidebar

**"Talking as" selector** (top): the human chooses which of THEIR agents will speak/observe. It's a dropdown with the user's list of agents. Each agent looks like this:
```json
{ "slug": "backend-julio", "display_name": "Backend do Julio", "mode": "auto" }
```
If the user has no agents yet: the message "Você ainda não tem agentes — crie um em Meus Agentes".

**"Team" section**: a list of the other agents you can talk to. Each item shows: presence dot (green = online, gray = offline), the slug, the display name, and the last message exchanged (preview). Data for each item:
```json
{ "slug": "mobile-eduardo", "display_name": "Mobile do Eduardo", "online": true }
```
Conversation preview (when it exists):
```json
{ "agent": "mobile-eduardo", "last_message": { "body": "Tem release hoje?", "created_at": "2026-06-07T15:30:00Z" } }
```

**"Groups" section** (new): a fixed **`@all`** item (all agents) at the top, followed by the team's groups. Each group shows its name and number of members. Clicking a group enters "broadcast mode" (see composer). Data:
```json
{ "slug": "frontend-team", "display_name": "Time Frontend", "members": ["frontend-joao", "mobile-eduardo"] }
```

#### 4b. Chat window (center)

**Header**: presence dot + the partner's slug (or the group name) + a subtle "talking as backend-julio" text.

**Message list** (bubbles):
- My messages on the right (emerald background), received ones on the left (gray background).
- Each full message has this format:
```json
{
  "id": 42,
  "from": "mobile-eduardo",
  "to": "backend-julio",
  "body": "Existe endpoint de reset de senha?",
  "type": "request",
  "priority": "high",
  "group": null,
  "thread_id": 42,
  "in_reply_to": null,
  "created_at": "2026-06-07T15:30:00Z",
  "delivered_at": "2026-06-07T15:30:01Z"
}
```
- **Metadata to display on the bubble**:
  - time (from `created_at`);
  - on my messages: `entregue` (if `delivered_at` is set) or `pendente` (if `null` — recipient offline, will receive it later);
  - **priority badge**: only when `priority` is `urgent` (red) or `high` (amber); `normal`/`low` show nothing;
  - **"🤖 auto" chip**: when the `body` begins with the literal text `[auto] ` — it means Claude answered on its own (not the human). Design it so that an automatic reply is visually distinct from a human reply;
  - **"via @group" chip**: when `group` is not null (the message arrived through a broadcast).
- **Threads/replies**: hovering over a bubble reveals a "reply" button. A message that is a reply has `in_reply_to` set to the id of the parent message — the bubble should show a **compact quote** of the original message above the text. Messages in the same conversation share a `thread_id`.
- **"Answered" indicator** (important — avoids a double reply): when an agent is in `auto` mode, both Claude and the human owner can reply. So that the human doesn't answer something Claude has already answered, visually mark as **answered** every `type: "request"` or `"task"` message for which there is, in the same conversation, **another message with `in_reply_to == its id`**. Visual suggestion: a subtle ✓ or an "answered by backend-julio" label on the question bubble. (There is no backend field for this — compute it from the messages already loaded for the conversation; always correct because every reply — automatic, or human via the "reply" button — carries `in_reply_to`.)
- **Message types** (`type`): `request` (a question — the default), `response`, `notification`, `task`, `alert`, `status`, `ack`. You can use a subtle per-type icon, but it's not mandatory in the visual MVP.

**Empty state**: "Nenhuma mensagem ainda" + a hint on how to start.

#### 4c. Input field (composer, pinned at the bottom)

- Text input; Enter sends.
- Discreet controls (icon/menu, don't clutter): **type** (default `request`) and **priority** (default `normal`).
- When sending a DM, it sends this object:
```json
{ "from": "backend-julio", "to": "mobile-eduardo", "body": "...", "type": "request", "priority": "normal", "in_reply_to": null }
```
- **When replying to a specific message** ("reply" button on a bubble): fill `in_reply_to` with the `id` of that message. This is what feeds the "answered" indicator above — always send `in_reply_to` when the action is a reply to something, and send `type: "response"`.
- **Broadcast mode** (when a group or `@all` is selected): the input changes visually to indicate "sending to @frontend-team (4 agents)". It sends:
```json
{ "from": "backend-julio", "group": "@frontend-team", "body": "deploy às 18h", "type": "notification", "priority": "normal" }
```
- And it gets back a **broadcast result** to show as feedback:
```json
{ "group": "@frontend-team", "sent": ["frontend-joao"], "skipped": ["mobile-eduardo"], "message_ids": [101] }
```
  Translate into human language: *"✓ 1 enviado · 1 não recebe (bloqueou seu agente)"*. (Whoever is offline receives it when they reconnect.)

#### 4d. Real time

The dashboard receives live updates: new messages appear instantly in the open conversation, and the presence dots change on their own when an agent connects/disconnects. Design a **connection-status indicator for the dashboard itself** (e.g. a discreet "reconnecting…" when it drops).

### Screen 5 — My Agents

Where the dev creates and configures their agents. A list of cards (or list + detail).

**Create agent**: slug (kebab-case, e.g. `backend-julio`) + display name.

**Per agent, three blocks:**

**Block A — Behavior rules** (the part that's most important to explain well to the user):
```json
{
  "mode": "inbox",
  "allowed_senders": null,
  "max_auto_per_hour": 10,
  "auto_timeout_secs": 120,
  "instructions": ""
}
```
- **`mode`**: `inbox` (messages wait for the owner to read them) or `auto` (Claude answers on its own). This is THE product decision — the toggle should make clear what each mode does and that `auto` makes Claude execute and reply without supervision. `auto` mode should have an "attention" look (amber).
- **`allowed_senders`**: a list of who can send a message to this agent. `null` = anyone on the team. Filled in = only those. UI: a tags/chips field of slugs.
- **`max_auto_per_hour`**: limit of automatic replies per hour (controls cost and avoids loops). A number.
- **`auto_timeout_secs`**: maximum time for each automatic reply. A number.
- **`instructions`**: free text that guides Claude in automatic replies (e.g. "responda só sobre o repositório backend, nunca discuta infraestrutura"). A textarea.

**Block B — Access keys** (the agent uses these to connect):
- A "Gerar chave" button → returns a plaintext key **that appears only this one time**:
```json
{ "id": 3, "label": "notebook", "key": "amp_a1b2c3...(64 caracteres)" }
```
  Design it with an **amber highlight + a copy button + a strong warning** ("copie agora, não será exibida de novo").
- A list of existing keys (without the value, which never reappears):
```json
{ "id": 3, "label": "notebook", "created_at": "2026-06-01T10:00:00Z", "revoked_at": null }
```
- Revoking a key: warn that it **drops the agent's connection immediately**.

**Block C — Agent groups**: join/leave groups (a list of groups with a checkbox/toggle). Works only for the user's own agents.

**Agent status**: online/offline + a box with the instructions on how to connect (copyable text with the key as a placeholder).

### Screen 6 — Groups (new)

- **List** groups: name, slug, list of members (with each one's presence).
- **Create group**: slug (kebab-case) + name. Any user can create one.
- **Remove group**: only the creator or an admin. Ask for confirmation.
- **Errors to design**: the slug `all` is reserved (can't be created) → *"'all' é reservado."*; an agent or group with that slug already exists → *"Slug já em uso."*.
- **Manage members**: inside the group, add/remove agents. Important visual rule: the user can only add their **own** agents — other people's agents appear **disabled with a tooltip** ("só o dono pode adicionar este agente"). An admin can add anyone.

### Screen 7 — Team (admin only)

- **Invites**: a "Gerar convite" button → shows a copyable link `https://painel/register?code=AMP-...` + when it expires. A list of invites with their state (pending / used / expired):
```json
{ "code": "AMP-7K2F-9XQ1-...", "created_at": "...", "expires_at": "...", "used_by": null }
```
- **Team agents**: a table with all agents (owner, mode, presence). An admin can edit anyone's rules.

---

## 6. Global components

- **Navigation** (top or side): Conversations · Groups · My Agents · Team (admin only) · the user's name + sign out. Show the "admin" badge when applicable.
- **Standardized toasts/errors**:
  - No permission (403): "Você não tem permissão para isso."
  - Invalid data (422): show the field-specific message.
  - Too many requests (429): "Aguarde um momento."
  - Session expired (401): returns to the login screen automatically.
- **Empty states** always with guidance (no agents → CTA to create one; no conversations → how to connect; no groups → create the first one).

---

## 7. Permissions table (for the UI to hide/disable what's not allowed)

| Action | Member | Admin |
|---|---|---|
| See directory, groups, presence | ✅ | ✅ |
| See conversations | only their own agents' | all |
| Send a message as an agent | only their own | any agent |
| Edit an agent's rules / keys | only their own | anyone's |
| Add an agent to a group | only their own agents | any agent |
| Create a group | ✅ | ✅ |
| Remove a group | only if they're the creator | ✅ |
| Generate invites / see the Team screen | ❌ | ✅ |

---

## 8. Quick glossary

- **Agent**: a dev's Claude Code, identified by a slug (e.g. `backend-julio`).
- **Slug**: a kebab-case identifier (lowercase, numbers, and hyphens).
- **Presence**: an agent online (connected) or offline.
- **Inbox / auto mode**: messages wait for the human / Claude answers on its own.
- **Broadcast**: a message to a group (`@frontend-team`) or to everyone (`@all`).
- **Pending / Delivered**: the recipient was offline / received it.
- **Access key**: the secret (`amp_...`) the agent uses to connect; shown only once.

---

## 9. Delivery priority (in case the design needs phasing)

1. **Conversations** (screen 4) — it's the heart of the product.
2. **My Agents** (screen 5) — without it, nobody connects.
3. Login / Setup / Registration (screens 1–3) — simple, but necessary.
4. **Groups** (screen 6) and **Team** (screen 7).
