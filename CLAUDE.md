# Ampla — Agent Messaging Platform

Slack/Discord for Claude Code agents: central hub (FastAPI + WS), local bridge (MCP + TS daemon), and web panel (React).

## Rule #1

**Read and follow `docs/ARCHITECTURE.md` to the letter.** The layering rules, WS protocol, testing and commit rules defined there are a contract — a violation is a bug, not a style choice.

## Rules summary (details in ARCHITECTURE.md)

- `hub/`: routes → services → repositories → models. A route never touches the database; a service never imports FastAPI.
- `bridge/`: the MCP server is stateless; all state lives in the daemon. `shared/protocol.ts` mirrors `hub/app/schemas/ws.py` — change one, change the other in the same commit.
- `web/`: components never `fetch` directly — only via `src/lib/api/` and `src/lib/ws/`.
- **Every feature ships with a test in the same commit** (unit and/or integration).
- Conventional Commits, one per feature: `feat(hub): ...`, `fix(bridge): ...`, `test(web): ...`.

## Commands

```bash
# hub
cd hub && source .venv/bin/activate
uvicorn app.main:app --reload          # dev server
pytest                                  # all tests
pytest tests/unit -x                    # unit only
ruff check app tests                    # lint (with security rules)
ruff format app tests                   # format
AMP_UPDATE_GOLDEN=1 pytest tests/golden # regenerate goldens (review the diff!)

# bridge
cd bridge
pnpm test                               # vitest (unit + integration + full-stack)
pnpm lint                               # biome
pnpm daemon                             # run the local daemon
pnpm build                              # tsc

# web
cd web
pnpm dev                                # vite dev server
pnpm test                               # vitest
pnpm lint                               # biome (react + a11y)
pnpm e2e                                # playwright
```

## Language

The project is open source and accepts outside contributions, so the **codebase speaks English to its contributors**:

- **English**: code comments, docstrings, test names/descriptions, documentation (`README.md`, `docs/`), and commit messages.
- **pt-BR (kept)**: strings the end user sees — UI labels and copy in `web/`, API/WS error messages returned to clients, daemon/CLI operator output, and the auto-responder prompt/persona sent to Claude. The **product** speaks Portuguese to its users; the **codebase** speaks English to its contributors. (UI i18n is a future option.)

Conversations with the maintainer may be in pt-BR.
