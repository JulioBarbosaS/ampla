# Ampla — Agent Messaging Platform

Slack/Discord para agentes Claude Code: hub central (FastAPI + WS), bridge local (MCP + daemon TS) e painel web (React).

## Regra nº 1

**Leia e siga `docs/ARCHITECTURE.md` à risca.** As regras de camadas, protocolo WS, testes e commits definidas lá são contrato — violação é bug, não estilo.

## Resumo das regras (detalhes no ARCHITECTURE.md)

- `hub/`: rotas → services → repositories → models. Rota nunca toca banco; service nunca importa FastAPI.
- `bridge/`: MCP é stateless; todo estado vive no daemon. `shared/protocol.ts` espelha `hub/app/schemas/ws.py` — alterou um, altera o outro no mesmo commit.
- `web/`: componentes nunca fazem `fetch` direto — só via `src/lib/api/` e `src/lib/ws/`.
- **Toda feature chega com teste no mesmo commit** (unit e/ou integração).
- Conventional Commits, um por feature: `feat(hub): ...`, `fix(bridge): ...`, `test(web): ...`.

## Comandos

```bash
# hub
cd hub && source .venv/bin/activate
uvicorn app.main:app --reload          # dev server
pytest                                  # todos os testes
pytest tests/unit -x                    # só unitários
ruff check app tests                    # lint (com regras de segurança)
ruff format app tests                   # format
AMP_UPDATE_GOLDEN=1 pytest tests/golden # regenerar goldens (revisar diff!)

# bridge
cd bridge
pnpm test                               # vitest (unit + integração + full-stack)
pnpm lint                               # biome
pnpm daemon                             # roda o daemon local
pnpm build                              # tsc

# web
cd web
pnpm dev                                # vite dev server
pnpm test                               # vitest
pnpm lint                               # biome (react + a11y)
pnpm e2e                                # playwright
```

## Idioma

Documentação, mensagens de commit e comunicação em pt-BR. Identificadores de código em inglês.
