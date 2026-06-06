/**
 * API local do daemon — consumida apenas pelo servidor MCP, via unix
 * socket 0600 (docs/ARCHITECTURE.md · Ameaça 4). Nunca abre porta TCP.
 */

import Fastify, { type FastifyInstance } from "fastify";
import { z } from "zod";
import type { MessageStore } from "./message-store.js";
import type { HubClient } from "./ws-client.js";

const sendBodySchema = z.object({
  to: z.string().min(3).max(50),
  body: z.string().min(1).max(16_384),
});

const readBodySchema = z.object({
  ids: z.array(z.number().int()),
});

export interface LocalApiDeps {
  agentId: string;
  hub: HubClient;
  store: MessageStore;
}

export function buildLocalApi({ agentId, hub, store }: LocalApiDeps): FastifyInstance {
  const api = Fastify({ logger: false });

  api.get("/status", async () => ({
    agent_id: agentId,
    connected: hub.connected,
    online: hub.onlineAgents(),
    settings: hub.settings,
    unread: store.unreadCount(),
  }));

  api.get("/presence", async () => ({ online: hub.onlineAgents() }));

  api.post("/send", async (request, reply) => {
    const parsed = sendBodySchema.safeParse(request.body);
    if (!parsed.success) {
      return reply.code(422).send({ error: parsed.error.issues[0]?.message ?? "inválido" });
    }
    const { to, body } = parsed.data;
    if (!hub.connected) {
      return reply.code(503).send({ error: "Daemon desconectado do hub." });
    }
    hub.send(to, body);
    store.append({
      id: null,
      from: agentId,
      to,
      body,
      ts: new Date().toISOString(),
      direction: "out",
      read: true,
    });
    return { sent: true, recipient_online: hub.onlineAgents().includes(to) };
  });

  api.get("/inbox", async (request) => {
    const query = request.query as { unread_only?: string; mark_read?: string };
    const unreadOnly = query.unread_only !== "false";
    const messages = store.inbox(unreadOnly);
    if (query.mark_read !== "false") {
      store.markRead(messages.map((m) => m.id));
    }
    return { messages };
  });

  api.post("/read", async (request, reply) => {
    const parsed = readBodySchema.safeParse(request.body);
    if (!parsed.success) {
      return reply.code(422).send({ error: "ids inválidos" });
    }
    store.markRead(parsed.data.ids);
    return { ok: true };
  });

  api.get("/history", async (request, reply) => {
    const query = request.query as { with?: string; limit?: string };
    if (!query.with) {
      return reply.code(422).send({ error: "parâmetro 'with' é obrigatório" });
    }
    const limit = Math.min(Number(query.limit ?? 50) || 50, 200);
    return { messages: store.conversation(query.with, limit) };
  });

  api.get("/partners", async () => ({ partners: store.partners() }));

  return api;
}
