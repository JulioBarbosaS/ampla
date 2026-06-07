# Plano — Fase 9: Confiabilidade do WS (ACK fim-a-fim + heartbeat)

> Não iniciado em código (revertido por limite de contexto). Este plano é o ponto de partida para retomar. Ordem: **ACK primeiro** (resolve perda de dados real), heartbeat depois. Lembrar: protocolo espelhado hub↔bridge **no mesmo commit**, goldens regenerados.

## Problema que resolve

Hoje o hub marca `delivered_at` quando o `send_json` ao socket retorna (`hub/app/api/routes/ws.py` · `_deliver`) — "empurrei pro cano", não "o destinatário gravou". Se o daemon cai antes de persistir, a mensagem fica marcada como entregue e **não volta no `pending`** → perda silenciosa. Falta também heartbeat → conexões zumbis ficam "online".

## Parte 1 — ACK fim-a-fim (at-least-once)

**Protocolo** (`hub/app/schemas/ws.py` + `bridge/src/shared/protocol.ts`, mesmo commit):
- Novo frame cliente→hub: `AckFrame { type:"ack", message_id:int }`. Adicionar ao `ClientFrame` union e ao `client_frame_adapter`.
- Espelhar em `protocol.ts` (não precisa entrar no `serverFrameSchema`, é client→hub).

**Hub** (`ws.py`):
- Renomear `_deliver` → `_dispatch(msg)`: envia ao socket do destinatário + espelha aos observers, **mas NÃO marca `delivered_at`** e **NÃO manda `delivered` ao remetente**. Retorna se o socket aceitou (para o broadcast_result.offline).
- No loop do agente (`_run_agent_connection`), tratar `AckFrame`: `mark_delivered([id])` → carregar msg → mandar `delivered{message_id,to}` ao `from_agent` se online → (opcional) re-espelhar aos observers com `delivered_at` preenchido.
- Flush de pending no hello: **remover** o `mark_delivered` automático (linhas ~133-140). As pending são enviadas; o daemon ackará cada uma.
- `_handle_send` e `_handle_broadcast`: usam `_dispatch`; o `delivered` ao remetente sai só no ack.

**Daemon** (`bridge/src/daemon/`):
- `ws-client.ts`: método `ackMessage(id: number)` que manda `{type:"ack", message_id:id}`.
- `index.ts` `hub.on("message")`: após `store.append(...)`, se `message.id != null` → `hub.ackMessage(message.id)`. **Sempre ackar** (mesmo se o append deduplicou), senão o hub reenvia para sempre. Dedup por id já existe no store → at-least-once correto.

**Testes a ATUALIZAR** (codificam o comportamento otimista atual — vão precisar ackar):
- `hub/tests/integration/test_ws.py`: `test_mensagem_roteada_em_tempo_real`, `test_historico_via_rest_apos_ws`, `test_threading_e_type_via_ws` → o destinatário (cliente de teste) deve mandar `ack` para o `delivered` chegar e o `delivered_at` ficar preenchido. Criar helper `ack(ws, message_id)` em `tests/helpers.py`.
- `test_destinatario_offline_recebe_no_proximo_hello` → na reconexão, ackar os pending antes de checar que a 2ª conexão vem vazia.
- Broadcast (`TestBroadcastWs`): `broadcast_result.offline` continua baseado em "socket não aceitou" (ack é assíncrono).
- Golden `hub/tests/golden/ws_frames.json`: adicionar `client.ack` (regenerar com `AMP_UPDATE_GOLDEN=1`).
- Bridge `protocol-mirror.test.ts`: cobrir `client.ack`.

**Teste novo (o que prova a correção):** mensagem entregue ao socket mas **sem ack** → reconectar → ela **volta no pending** (não foi perdida). Hoje isso falharia (marcada como entregue cedo).

## Parte 2 — Heartbeat (~30s)

Starlette não expõe ping/pong nativo no loop `receive_text()` facilmente → usar **heartbeat de aplicação** (frames JSON):
- Frames: hub→cliente `{type:"ping"}` (novo `PingFrame` server) e cliente→hub `{type:"pong"}` (`PongFrame` client).
- Hub: task asyncio concorrente ao loop de recepção que manda `ping` a cada `AMP_HEARTBEAT_SECS` (default 30); se passar 2 intervalos sem `pong`, fecha o ws (e o `finally` já difunde offline). Cuidado com a concorrência: o loop principal lê e atualiza `last_pong`; a task de ping verifica.
- Daemon (`ws-client.ts`): ao receber `ping`, responde `pong` imediatamente. Opcional: o daemon também detecta hub morto se não receber ping em 2 intervalos.
- Config: `AMP_HEARTBEAT_SECS` em `hub/app/core/config.py`.
- Testes: ping é enviado; sem pong → conexão cai. Pode usar intervalo curto no `make_settings`.

## Inspiração (pesquisa)

- ACK + dedup por id = **at-least-once** (Socket.IO, Microsoft Azure Web PubSub, WebSocket.org reconnection).
- Heartbeat 20–45s (WebSocket.org Heartbeat, Ably).
- Convergência de design: "Agent Message Bus" (dev.to/linou518) tem `/ack` e heartbeat — mesma direção.

## Checklist de saída
- [ ] hub + bridge no mesmo commit (protocolo espelhado)
- [ ] goldens regenerados e diff revisado
- [ ] testes verdes nas 3 partes; coverage gates intactos
- [ ] ARCHITECTURE.md · Protocolo WS atualizado (frames ack/ping/pong; semântica nova de delivered_at)
