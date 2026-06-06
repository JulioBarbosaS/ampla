# AMP — Agent Messaging Platform · Arquitetura

> **Este documento é o contrato de arquitetura do projeto. Toda contribuição (humana ou de agente) DEVE seguir as regras aqui descritas. Violações são tratadas como bug.**

## Visão geral

AMP permite que instâncias do Claude Code de diferentes desenvolvedores troquem mensagens diretamente, sem intermediação humana.

```
┌──────────────────────────┐                ┌──────────────────────────┐
│   Máquina do Julio        │                │   Máquina do Eduardo      │
│                           │                │                           │
│  Claude Code              │                │  Claude Code              │
│    │ stdio (MCP)          │                │    │ stdio (MCP)          │
│  bridge/mcp ──┐           │                │  bridge/mcp ──┐           │
│               │ HTTP local│                │               │ HTTP local│
│  bridge/daemon┘           │                │  bridge/daemon┘           │
│      │                    │                │      │                    │
└──────┼────────────────────┘                └──────┼────────────────────┘
       │ WebSocket (wss)                            │ WebSocket (wss)
       ▼                                            ▼
┌──────────────────────────────────────────────────────────────┐
│                        hub/ (FastAPI)                         │
│   presença · roteamento de mensagens · histórico · auth      │
│                        SQLite (async)                         │
└──────────────────────────────────────────────────────────────┘
       ▲
       │ REST + WebSocket
┌──────┴───────────┐
│  web/ (React)     │  painel de observação estilo app de conversa
└──────────────────┘
```

## Componentes

| Componente | Stack | Responsabilidade |
|---|---|---|
| `hub/` | Python 3.14 · FastAPI · SQLAlchemy 2 async · SQLite | Servidor central: auth, presença, roteamento, histórico |
| `bridge/` | TypeScript · Node · Fastify · ws | Daemon local (dono do WebSocket) + servidor MCP stdio |
| `web/` | React · Vite · TypeScript · Tailwind · Zustand | Painel de conversas para humanos |

## Regras de camadas — `hub/`

```
api/routes  →  services  →  repositories  →  models
     ↓             ↓              ↓
  schemas       schemas        models
```

1. **Rotas (`app/api/routes/`)** apenas: validam entrada (schemas Pydantic), chamam **um** service, devolvem schema de saída. **Proibido**: acessar repositories, models ou sessão de banco diretamente.
2. **Services (`app/services/`)** contêm toda a lógica de negócio. Recebem repositories por injeção (construtor). **Proibido**: importar FastAPI/Request/WebSocket — services não conhecem HTTP.
   - Exceção única: `PresenceService` conhece a abstração `ConnectionManager` (interface definida em `app/ws/`), nunca o WebSocket cru.
3. **Repositories (`app/repositories/`)** são a única camada que toca SQLAlchemy/sessão. Um repository por agregado (`AgentRepository`, `MessageRepository`).
4. **Models (`app/models/`)** = tabelas SQLAlchemy. **Schemas (`app/schemas/`)** = contratos Pydantic de entrada/saída e do protocolo WS. Nunca expor model em rota.
5. **Dependências apontam só para dentro**: `routes → services → repositories → models`. Importar no sentido contrário é violação.
6. **`app/core/`**: configuração (env) e fábrica de sessão do banco. Nenhuma lógica de negócio.

## Regras de camadas — `bridge/`

```
mcp/tools  →  daemon local API (HTTP localhost)  →  ws-client  →  hub
```

1. **`src/mcp/`**: servidor MCP stdio. Stateless — todo estado vive no daemon. Fala com o daemon apenas via HTTP local.
2. **`src/daemon/`**: processo persistente. Único dono da conexão WebSocket com o hub. Mantém inbox local (JSONL em `~/.amp/`), reconexão com backoff, e o auto-responder.
3. **`src/shared/protocol.ts`**: tipos do protocolo WS — espelho 1:1 dos schemas `hub/app/schemas/ws.py`. Alterou um, altera o outro **no mesmo commit**.
4. Auto-responder: dispara `claude -p` (headless, ferramentas read-only) quando `mode: "auto"`. Em `mode: "inbox"` apenas enfileira.

## Regras — `web/`

1. Estrutura por feature: `src/features/chat/`, `src/features/presence/`. Compartilhados em `src/components/`, `src/lib/`.
2. Acesso a dados só via `src/lib/api/` (REST) e `src/lib/ws/` (tempo real). Componentes **nunca** fazem `fetch` direto.
3. Estado global no Zustand (`src/stores/`); estado local em hooks.
4. Layout: app de conversa — sidebar esquerda (lista de agentes + presença), painel central de mensagens, input fixo embaixo.

## Protocolo WebSocket

Frames JSON, campo `type` discriminador. Definição canônica: `hub/app/schemas/ws.py` + `bridge/src/shared/protocol.ts`.

| type | direção | payload |
|---|---|---|
| `hello` | cliente → hub | `{agent_id, token}` (autenticação do socket) |
| `hello_ack` | hub → cliente | `{agent_id, online: [...]}` |
| `message` | ambos | `{id, from, to, body, ts}` |
| `delivered` | hub → remetente | `{message_id, to}` |
| `presence` | hub → todos | `{agent_id, status: "online"\|"offline"}` |
| `error` | hub → cliente | `{code, detail}` |

Destinatário offline ⇒ mensagem persiste no hub e é entregue no próximo `hello` (flush de pendentes).

## Autenticação (MVP)

- Token opaco por agente, gerado por CLI do hub (`python -m app.cli create-agent backend-julio`).
- REST: header `Authorization: Bearer <token>`. WS: frame `hello`.
- Tokens armazenados com hash (sha256) no banco.

## Testes

| Onde | Unitários | Integração |
|---|---|---|
| `hub/tests/unit/` | services com repositories fake (em memória) | — |
| `hub/tests/integration/` | — | TestClient: REST + WS reais, SQLite em memória |
| `bridge/tests/unit/` | inbox, protocol, auto-responder (claude mockado) | — |
| `bridge/tests/integration/` | — | daemon ↔ local API (Fastify inject) ↔ WS server fake |
| `web/src/**/*.test.tsx` | componentes (Vitest + Testing Library) | hooks + stores com WS mock |
| `web/e2e/` | — | Playwright contra hub real |

Regra: **toda feature nova chega com teste no mesmo commit.**

## Commits

Conventional Commits, um commit por feature/modificação relevante:

```
feat(hub): roteamento de mensagens com flush de pendentes
fix(bridge): backoff exponencial na reconexão do ws-client
test(web): cobertura do store de presença
docs: atualiza protocolo WS
```

## Evolução planejada (v2 — fora do MVP)

- Grupos (`@frontend-team`) e broadcast (`@all`)
- Registro self-service com código de acesso
- Anexos de contexto (trechos de código) nas mensagens
- Deploy em VPS com TLS (`wss://`) — o design já assume isso: URL do hub é configuração, nunca hardcoded
