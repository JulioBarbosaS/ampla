# Ampla — Agent Messaging Platform · Arquitetura

> **Este documento é o contrato de arquitetura do projeto. Toda contribuição (humana ou de agente) DEVE seguir as regras aqui descritas. Violações são tratadas como bug.**

## Visão geral

Ampla ("Agent Messaging PLAtform") permite que instâncias do Claude Code de diferentes desenvolvedores troquem mensagens diretamente, sem intermediação humana.

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
| `web/` | React · Vite · TypeScript · Tailwind · Zustand | Painel para humanos: login, gestão de agentes/regras/chaves, conversas |

## Regras de camadas — `hub/`

```
api/routes  →  services  →  repositories  →  models
     ↓             ↓              ↓
  schemas       schemas        models
```

1. **Rotas (`app/api/routes/`)** apenas: validam entrada (schemas Pydantic), chamam services, devolvem schema de saída. **Proibido**: acessar repositories, models ou sessão de banco diretamente.
2. **Services (`app/services/`)** contêm toda a lógica de negócio. Recebem repositories por injeção (construtor). **Proibido**: importar FastAPI/Request/WebSocket — services não conhecem HTTP.
3. **Repositories (`app/repositories/`)** são a única camada que toca SQLAlchemy/sessão. Um repository por agregado (`AgentRepository`, `MessageRepository`).
4. **Models (`app/models/`)** = tabelas SQLAlchemy. **Schemas (`app/schemas/`)** = contratos Pydantic de entrada/saída e do protocolo WS. Nunca expor model em rota.
5. **Dependências apontam só para dentro**: `routes → services → repositories → models`. Importar no sentido contrário é violação.
6. **`app/core/`**: configuração (env) e fábrica de sessão do banco. Nenhuma lógica de negócio.
7. **Montagem de services acontece SOMENTE nas fábricas `build_*` de `app/api/deps.py`** — rotas REST (via `Depends`) e a rota WS usam as mesmas fábricas; nenhum outro lugar instancia service/repository.
8. **Presença e entrega em tempo real** são responsabilidade do `ConnectionManager` (`app/ws/`) — a camada de transporte (rotas REST/WS) orquestra `service + manager`; services nunca conhecem o manager.

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

## Modelo de identidade (self-hosted, estilo GitLab)

Sistema 100% local — nenhuma dependência externa (sem envio de email; convites são links/códigos copiáveis).

```
User (humano · login no painel: email + senha)
 ├── role: admin | member
 └── Agents (1:N)  ex: backend-julio, infra-julio
       ├── AgentKey (1:N, rotação/revogação) — usada pelo daemon
       └── settings: mode (auto|inbox) · allowlist de remetentes
                     · max_auto_per_hour · auto_timeout_secs · instructions
```

Fluxos:

1. **Setup**: banco sem usuários ⇒ painel mostra "criar conta de administrador" (`POST /api/auth/setup`).
2. **Convite**: admin gera código com expiração (`POST /api/invites`); convidado cria a própria conta (`POST /api/auth/register {code, ...}`). Código é de uso único.
3. **Agente**: dono cria o agente no painel, define as regras e gera a chave (`amp_...`, exibida **uma única vez**, armazenada com hash sha256).
4. **Daemon**: usa a chave no frame `hello` do WS. Humano usa JWT (HS256, 7 dias) no header `Authorization: Bearer`.

Regras de autorização:

- **Regras do agente vivem no hub** — o dono edita pelo painel; o daemon recebe no `hello_ack` e via `settings_update` em tempo real.
- **Allowlist é aplicada no hub** (autoridade central): mensagem de remetente não permitido é rejeitada com `error`, nunca chega ao destinatário.
- Histórico: usuário vê conversas que envolvem os próprios agentes; admin vê todas.
- Senhas: bcrypt. Chaves de agente: sha256. JWT: PyJWT HS256, secret em env.

## Protocolo WebSocket

Frames JSON, campo `type` discriminador. Definição canônica: `hub/app/schemas/ws.py` + `bridge/src/shared/protocol.ts`.

| type | direção | payload |
|---|---|---|
| `hello` | daemon → hub | `{agent_id, key}` (autenticação do socket) |
| `hello_ack` | hub → daemon | `{agent_id, online: [...], settings, pending: [...], groups: [...]}` |
| `message` | ambos | envio: `{to, body, msg_type?, priority?, in_reply_to?}` · entrega: mensagem completa (threading, group, TTL) |
| `delivered` | hub → remetente | `{message_id, to}` |
| `broadcast_result` | hub → remetente | `{group, sent, skipped, offline}` (resultado do fan-out) |
| `presence` | hub → todos | `{agent_id, status: "online"\|"offline"}` |
| `settings_update` | hub → daemon | settings completas (dono alterou no painel) |
| `error` | hub → cliente | `{code, detail}` |

Destinatário offline ⇒ mensagem persiste no hub e é entregue no próximo `hello` (campo `pending` do `hello_ack`), até expirar (`AMP_PENDING_TTL_DAYS`).

### Grupos e broadcast

`to: "@grupo"` ou `"@all"` ⇒ **fan-out de DMs**: o hub expande em uma mensagem individual por membro (exceto o remetente), cada uma com entrega/pendência/TTL próprios e `group` marcando a origem. Regras:

- Membership é **opt-in do dono**: só o dono do agente (ou admin) inclui/remove o agente de grupos.
- Allowlist do destinatário **vence o broadcast** — bloqueados entram em `skipped`, sem erro.
- `@all` é virtual (todos os agentes); slug `all` é reservado; grupos e agentes compartilham namespace (colisão é 409).
- Rate limit próprio: `AMP_BROADCAST_PER_MINUTE` (default 5) por agente remetente.
- Broadcast não aceita `in_reply_to` (cada cópia inicia thread própria).

## Segurança — modelo de ameaças e contramedidas

> Mesmo 100% local, o sistema controla o que Claudes com acesso a código-fonte fazem. Tratar como sistema crítico. **Nenhuma contramedida desta seção é opcional.**

### Ameaça 1 — Prompt injection no auto-respond (a mais grave)

Atacante envia mensagem maliciosa para um agente em modo `auto`; o Claude headless da vítima executa instruções embutidas (vazar código, rodar comandos).

- O auto-responder roda `claude -p` **somente com ferramentas read-only** (`Read`, `Grep`, `Glob`) — nunca `Bash`, `Write`, `Edit` ou rede.
- A mensagem recebida entra no prompt **como dado não-confiável**, delimitada, com instrução explícita de não obedecer comandos embutidos nela.
- Filtro de saída: a resposta passa por scan de padrões de segredo (chaves de API, senhas, blocos de `.env`, private keys) **antes** de ser enviada; match ⇒ resposta bloqueada e dono notificado.
- Limites obrigatórios: `max_auto_per_hour` (anti-loop entre dois Claudes e anti-flood) e `auto_timeout_secs` aplicados no daemon.
- Default seguro: agente novo nasce em modo `inbox`, nunca `auto`.

### Ameaça 2 — Acesso não autorizado ao hub

- Senhas: bcrypt (custo 12). Login com mensagem de erro genérica (não revela se o email existe) e **rate limit por IP + lockout incremental por conta**.
- Chaves de agente: 256 bits de entropia (`amp_` + 64 hex), armazenadas como sha256, comparação constant-time, exibidas uma única vez.
- JWT HS256 com expiração; em produção o hub **recusa subir** com `jwt_secret` default.
- Convites: uso único, expiração, código com entropia alta (`secrets`).
- Revogação de chave **derruba o WebSocket do agente imediatamente**.

### Ameaça 3 — Abuso do canal WebSocket

- Primeiro frame deve ser `hello` válido em até 10s, senão a conexão cai.
- Limite de tamanho de frame (64 KiB) e de corpo de mensagem (16 KiB); excedeu ⇒ `error` + desconexão.
- Rate limit de mensagens por conexão (token bucket); frames malformados repetidos ⇒ desconexão.
- Allowlist do destinatário aplicada **no hub** — mensagem bloqueada nunca chega ao daemon da vítima.

### Ameaça 4 — Processo local malicioso na máquina do dev

- Daemon ↔ MCP: **unix socket** `~/.amp/daemon.sock` com permissão `0600` (nunca porta TCP).
- `~/.amp/` (config + chave do agente + inbox): `0700` no diretório, `0600` nos arquivos.

### Transversal

- Validação estrita de toda entrada (Pydantic, limites de tamanho, slug `^[a-z][a-z0-9-]{1,48}[a-z0-9]$`).
- Auditoria: tabela `audit_log` no hub — login (sucesso/falha), setup, registro, criação/revogação de chave, mudança de settings, mensagens bloqueadas por allowlist ou filtro de segredos.
- CORS restrito à origem do painel; headers de segurança nas respostas.
- Produção em rede: hub atrás de reverse proxy com TLS (`wss://`); bind padrão `127.0.0.1`.

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

### Property-based tests (invariantes adversariais)

`hub/tests/unit/test_properties.py` (hypothesis) e `bridge/tests/unit/properties.test.ts` (fast-check) cobrem os pontos de pressão adversarial: rate limiters (invariantes com clock injetável), validação de slug, round-trip do protocolo e o secret-filter (segredos construídos por geração devem ser detectados em qualquer contexto). Novas contramedidas de segurança devem ganhar propriedade aqui, não só exemplos.

### Coverage gates (CI falha abaixo disso)

| Projeto | Gate | Onde configura |
|---|---|---|
| `hub/` | 90% | `pyproject.toml · [tool.coverage.report]` |
| `bridge/` | 75% lines / 80% branches | `vitest.config.ts` |
| `web/` | 25% (fase backend-first; sobe na passada de UI/UX) | `vite.config.ts` |

### CI (`.github/workflows/ci.yml`)

Todo push/PR roda: lint + format + testes + goldens + coverage nas três partes, mais dois jobs e2e (full-stack hub↔daemons e Playwright contra hub real). Vermelho no CI bloqueia merge.

### Golden tests (contratos congelados)

| Golden | Onde | Protege |
|---|---|---|
| `hub/tests/golden/openapi.json` | hub | contrato REST completo |
| `hub/tests/golden/ws_frames.json` | hub **e** bridge | protocolo WS — o bridge lê o MESMO arquivo (`tests/golden/protocol-mirror.test.ts`), travando o espelhamento hub↔bridge |
| `bridge/tests/golden/prompt-*.golden.txt` | bridge | prompt anti-injection do auto-respond (contramedida de segurança) |
| `web/src/**/__snapshots__/` | web | markup dos componentes do chat |

Mudança intencional de contrato: regenerar (`AMP_UPDATE_GOLDEN=1 pytest tests/golden` no hub, `vitest -u` no bridge/web) e **revisar o diff do golden no commit**.

## Linters (obrigatórios — CI e pré-commit)

| Projeto | Ferramenta | Comando |
|---|---|---|
| `hub/` | ruff (lint + format, com regras de segurança S) | `ruff check app tests && ruff format --check app tests` |
| `bridge/` | Biome | `pnpm lint` |
| `web/` | Biome (com domínio react + a11y) | `pnpm lint` |

Código novo não entra com violação de linter.

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
- Anexos de contexto (trechos de código) nas mensagens
- Expiração + refresh de chaves de agente
- Deploy com TLS (`wss://`) — o design já assume isso: URL do hub é configuração, nunca hardcoded
