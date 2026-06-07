/**
 * API local do daemon — consumida apenas pelo servidor MCP, via unix
 * socket 0600 (docs/ARCHITECTURE.md · Ameaça 4). Nunca abre porta TCP.
 */

import Fastify, { type FastifyInstance } from "fastify";
import { z } from "zod";
import { messageTypeSchema, prioritySchema } from "../shared/protocol.js";
import type { MessageStore } from "./message-store.js";
import type { HubClient } from "./ws-client.js";

const sendBodySchema = z.object({
  // agente ("backend-julio") ou grupo ("@frontend-team", "@all")
  to: z
    .string()
    .min(3)
    .max(51)
    .regex(/^@?[a-z][a-z0-9-]*$/, "destinatário inválido"),
  body: z.string().min(1).max(16_384),
  type: messageTypeSchema.default("request"),
  priority: prioritySchema.default("normal"),
  in_reply_to: z.number().int().optional(),
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

  api.get("/groups", async () => ({ groups: hub.groups }));

  api.post("/send", async (request, reply) => {
    const parsed = sendBodySchema.safeParse(request.body);
    if (!parsed.success) {
      return reply.code(422).send({ error: parsed.error.issues[0]?.message ?? "inválido" });
    }
    const { to, body, type, priority, in_reply_to } = parsed.data;
    if (!hub.connected) {
      return reply.code(503).send({ error: "Daemon desconectado do hub." });
    }
    const isBroadcast = to.startsWith("@");
    hub.send(to, body, {
      msgType: type,
      priority,
      ...(in_reply_to !== undefined ? { inReplyTo: in_reply_to } : {}),
    });
    store.append({
      id: null,
      from: agentId,
      to,
      body,
      type,
      priority,
      group: isBroadcast ? to : null,
      thread_id: null,
      in_reply_to: in_reply_to ?? null,
      ts: new Date().toISOString(),
      direction: "out",
      read: true,
    });
    return {
      sent: true,
      broadcast: isBroadcast,
      recipient_online: isBroadcast ? null : hub.onlineAgents().includes(to),
    };
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
