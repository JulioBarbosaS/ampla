# Plan — Agent onboarding + real smoke test

> The two steps that turn "infrastructure ready and tested with mocks" into "Claudes actually talking". Run with fresh context. Do the **smoke test first** (it reveals what's actually missing), then the onboarding (it fixes the gap the smoke test will expose).

## Problem

Everything is green in the tests, but: (1) the real `claude -p`, the real MCP server, and the daemon-as-a-service **have never actually been turned on** — auto-respond only ran with a mocked runner; (2) even once turned on, the Claude on the other side **doesn't know it's a member of the Ampla network** — the MCP tools show up (auto-discovery), but nothing teaches Claude *when/why* to use them or that it should answer messages. The "onboarding" is missing.

## Part A — Real smoke test (do first, manual + assisted)

Goal: prove (or break) the `@backend` → real auto-respond → reply flow.

Steps:
1. Bring up the real hub: `cd hub && .venv/bin/uvicorn app.main:app --port 4455` (with AMP_JWT_SECRET set).
2. Create an admin + 2 agents (`backend-julio`, `mobile-eduardo`) + keys via REST/dashboard.
3. Bring up 2 real daemons with separate `AMP_HOME`, `project_dir` pointing at real repos, `claude_bin` = path to `claude`.
4. Put `backend-julio` in `auto` mode (dashboard/PATCH).
5. From the mobile's daemon, send via the local API: `POST /send {to: backend-julio, body: "existe endpoint de reset de senha?"}`.
6. **Observe**: does the backend's daemon fire the real `claude -p` → read the code → reply? Does the reply come back to the mobile's inbox?

What will probably break (verify/adjust): the `claude -p` flags (they may have changed: `--allowedTools`, `--print`, output format — confirm with `claude --help`); stdout parsing (today it expects plain text — `claude -p` may emit JSON with `--output-format`); the `cwd`/permissions; timing (the 120s timeout may be too short on the first call). **Record each adjustment as a fix with a test.**

Expected result: a short "how to run locally" doc in the README + adjustments to `defaultClaudeRunner` if needed.

## Part B — Agent onboarding (SessionStart hook)

Goal: Claude Code "wakes up" aware that it's an agent on the Ampla network.

- A new hook `bridge/hooks/amp-session-start.sh` (Claude Code's `SessionStart` event) that queries the daemon (`GET /status`, `/presence`, `/inbox`) and injects into the context via `hookSpecificOutput.additionalContext`:
  ```
  Você é o agente "backend-julio" na rede Ampla da equipe.
  Colegas online agora: mobile-eduardo, infra-maria.
  Você tem N mensagem(ns) não lida(s).
  Use amp_send para perguntar/responder a outros agentes; amp_inbox para ler; amp_presence para ver quem está online.
  Quando tiver dúvida sobre outro serviço, pergunte ao agente responsável em vez de adivinhar.
  ```
- Fails silently (exit 0) if the daemon isn't running — just like `amp-inbox.sh`.
- Document in the README the installation of BOTH hooks (`SessionStart` + `UserPromptSubmit`) in `.claude/settings.json`.
- (Optional) the dashboard shows a "suggested CLAUDE.md snippet" when creating the agent, as an explicit alternative to the hook.

No change to the hub/protocol — it's just bridge (a new hook) + docs. Test: the script, given a fake daemon/fixture, produces the expected context JSON (it can be a simple shell test or a vitest that invokes the script).

## Order and checklist
- [x] **Real runner validated** (`tests/integration/claude-runner.test.ts`): non-mocked spawn, prompt via `-p`, stdout parsing, timeout, exit code, cwd — with a fake `claude` (without spending money on the account).
- [x] B1 hook `amp-session-start.sh` + e2e test
- [x] B2 README: install the 2 hooks
- [x] **A-interactive (real smoke, 2026-06-07):** real hub + 2 real daemons (`backend-julio` in `auto`, `mobile-eduardo` in `inbox`) + the REAL `claude -p` in the hub's `project_dir`. A question was fired via the local API `/send` → auto-respond read the code (read-only) and answered correctly in ~8–12s, round-trip through the inbox. Validated: flags (`--allowedTools Read,Grep,Glob --disallowedTools Bash,Write,...`), plain-text output (no `--output-format`), security prompt respected, secret filter with no blocking, threading (`type`/`priority`/`in_reply_to`/`thread_id`), clean detached spawn (zero orphaned `claude`). **No adjustment to `defaultClaudeRunner` was needed.**
- [x] **MCP shell validated (2026-06-07):** (1) automated test `tests/integration/mcp-server.test.ts` — real MCP client ↔ `buildServer()` ↔ live daemon: `tools/list` (6 `amp_*` tools), `amp_status`/`amp_inbox`/`amp_send` through the unix socket all the way to the hub, and the error path. (2) REAL `claude`: `claude mcp add ampla` → `claude mcp list` = **✓ Connected** (MCP handshake) → `claude -p` invoking `mcp__ampla__amp_status` answered with real daemon data ("agent_id backend-julio, connected, inbox mode"). The smoke environment was clean at the end (processes, MCP registrations, and the temp dir).
- [ ] **Hooks active in an interactive `claude` session.** `amp-session-start.sh` has an e2e test (`session-start-hook.test.ts`) proving the context JSON; all that's left is to install them in the project's `.claude/settings.json` and see the onboarding/inbox in an interactive session (a user installation step, not a code one).

**What remains is user installation/observation** (the 2 hooks in the `settings.json` of an interactive session) — the daemon→`claude -p`→delivery path **and** the MCP shell→daemon→hub are proven end-to-end, automated, and with the real `claude`.

### Smoke finding: `dist/` was stale
The first run ran an old build (the prompt said "AMP", `type`/`thread_id` came out `null`) — the `bridge/dist/` wasn't keeping up with `src/` after the rename/threading. Fixed with `pnpm build` and revalidated. **Lesson:** `dist/` is not versioned; a production daemon should come up from a fresh build (or from `tsx src/`). It's worth adding a build step in the deploy/systemd so it doesn't run stale code.

## Why in this order
The smoke test reveals whether the real `claude -p` works (the foundation). A perfect onboarding is useless if auto-respond breaks on the first real call. Then onboarding closes the "Claude doesn't know it should use the network" gap — which the smoke test itself will lay bare.
