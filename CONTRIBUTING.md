# Contributing to Ampla

Thanks for your interest! Ampla is a self-hosted messaging platform for Claude
Code agents, made of three packages: `hub/` (FastAPI + WebSocket), `bridge/`
(TypeScript daemon + MCP server) and `web/` (React panel).

## Ground rules

These are a contract, not style preferences — a PR that breaks them won't merge:

1. **Read [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) first.** The layering,
   the WS protocol and the threat model are defined there.
   - `hub/`: routes → services → repositories → models. A route never touches
     the database; a service never imports FastAPI.
   - `bridge/`: the MCP server is stateless; all state lives in the daemon.
     `shared/protocol.ts` mirrors `hub/app/schemas/ws.py` — change one, change
     the other in the **same commit** (a golden test enforces it).
   - `web/`: components never `fetch` directly — only via `src/lib/api/` and
     `src/lib/ws/`.
2. **Every feature ships with a test in the same commit** (unit and/or
   integration). Bug fixes ship with a regression test.
3. **Lint and format must pass** (`ruff` for the hub, `biome` for bridge/web).
4. **Security matters even though it's local.** Outsiders controlling what the
   agents reply is dangerous — be rigorous. Never commit secrets, credentials,
   or database files.
5. **Conventional Commits, one per feature**: `feat(hub): ...`,
   `fix(bridge): ...`, `test(web): ...`, `docs: ...`, `ci: ...`.

## Language

The project is open source and accepts outside contributions, so the
**codebase speaks English to its contributors**:

- **English**: code, comments, docstrings, test names/descriptions,
  documentation and commit messages.
- **pt-BR (kept)**: strings the end user sees — UI labels/copy in `web/`,
  API/WS error messages, daemon/CLI operator output, and the auto-responder
  persona. The product speaks Portuguese to its users; the codebase speaks
  English to its contributors.

## Local setup

```bash
# hub
cd hub && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest                 # tests
.venv/bin/ruff check app tests   # lint
.venv/bin/ruff format app tests  # format

# bridge
cd bridge && pnpm install
pnpm test        # vitest (unit + integration + full-stack)
pnpm lint        # biome

# web
cd web && pnpm install
pnpm dev         # vite dev server (proxies /api and /ws to the hub)
pnpm test        # vitest
pnpm lint        # biome
pnpm e2e         # playwright (spins up a real hub)
```

### One command for all gates

`scripts/ci.sh` runs every gate — the **same checks** the GitHub Actions
workflow runs, but on plain local git (no remote required):

```bash
scripts/ci.sh          # core: lint + format + types + tests (offline)
scripts/ci.sh --audit  # + supply-chain audits (pip-audit, pnpm audit)
scripts/ci.sh --e2e    # + real end-to-end (full-stack daemons + Playwright)
scripts/ci.sh --all    # everything
```

Wire it as a pre-push gate once (so a broken push can't leave your machine):

```bash
git config core.hooksPath .githooks   # runs scripts/ci.sh before every push
git push --no-verify                  # bypass once, in an emergency
```

`scripts/ci.sh` and `.github/workflows/ci.yml` mirror each other — a gate added
to one belongs in the other.

The full suite (lint + tests + coverage + e2e) also runs in CI on every PR. If
you change the OpenAPI surface or a golden, regenerate it and **review the
diff**: `AMP_UPDATE_GOLDEN=1 pytest tests/golden`.

## Submitting

1. Fork, branch from `main`, make your change with its test.
2. Ensure lint + tests are green in the affected package(s).
3. Open a PR describing the change and why. Keep it focused — one feature per PR.

By contributing you agree your work is licensed under the project's
[MIT license](LICENSE).
