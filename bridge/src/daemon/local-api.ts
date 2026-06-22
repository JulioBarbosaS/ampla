/**
 * Daemon local API — consumed only by the MCP server, over a 0600 unix
 * socket (docs/ARCHITECTURE.md · Threat 4). Never opens a TCP port.
 */

import Fastify, { type FastifyInstance } from "fastify";
import { z } from "zod";
import { messageTypeSchema, prioritySchema } from "../shared/protocol.js";
import type { MessageStore } from "./message-store.js";
import type { HubClient } from "./ws-client.js";

const sendBodySchema = z.object({
  // agent ("backend-julio") or group ("@frontend-team", "@all")
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

// Delegation target is a single agent (never a group/@all) — handing a task off
// to "everyone" makes no sense (Epic 04 · 4.4).
const delegateBodySchema = z.object({
  to: z
    .string()
    .min(3)
    .max(50)
    .regex(/^[a-z][a-z0-9-]*$/, "destinatário inválido (use o slug de um agente)"),
  task: z.string().min(1).max(2_000),
  context: z.string().max(16_384).default(""),
});

// Kanban write payloads (Epic 06 · 6.4) — mirror the hub schemas (defense in
// depth). The hub re-validates and enforces the per-agent capability; these
// just reject obvious junk before it leaves the daemon.
const kanbanCreateCardSchema = z.object({
  board_id: z.number().int(),
  title: z.string().min(1).max(200),
  body: z.string().max(16_384).default(""),
  column_id: z.number().int().optional(),
  assignee: z.string().max(60).optional(),
  priority: prioritySchema.default("normal"),
});
const kanbanMoveCardSchema = z.object({
  board_id: z.number().int(),
  card_id: z.number().int(),
  to_column_id: z.number().int(),
  before_id: z.number().int().optional(),
  after_id: z.number().int().optional(),
  expected_version: z.number().int().min(1),
});
const kanbanCommentSchema = z.object({
  board_id: z.number().int(),
  card_id: z.number().int(),
  body: z.string().min(1).max(16_384),
});

/** Drops `undefined` keys so the WS frame mirrors what the hub's optional fields
 * expect (omitted, not null). */
function compact(obj: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(obj).filter(([, v]) => v !== undefined));
}

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

  api.post("/delegate", async (request, reply) => {
    const parsed = delegateBodySchema.safeParse(request.body);
    if (!parsed.success) {
      return reply.code(422).send({ error: parsed.error.issues[0]?.message ?? "inválido" });
    }
    const { to, task, context } = parsed.data;
    if (to === agentId) {
      return reply.code(422).send({ error: "Não dá para delegar para o próprio agente." });
    }
    if (!hub.connected) {
      return reply.code(503).send({ error: "Daemon desconectado do hub." });
    }
    hub.sendDelegate(to, task, context);
    // Mirror the hand-off into the local history (like /send) so amp_history with
    // the delegate shows the outgoing task. The hub is the source of truth.
    const body = context.trim() ? `${task.trim()}\n\nContexto:\n${context.trim()}` : task.trim();
    store.append({
      id: null,
      from: agentId,
      to,
      body,
      type: "task",
      priority: "normal",
      group: null,
      thread_id: null,
      in_reply_to: null,
      ts: new Date().toISOString(),
      direction: "out",
      read: true,
    });
    return { delegated: true, to, recipient_online: hub.onlineAgents().includes(to) };
  });

  // ---- kanban (Epic 06 · 6.4): writes over the WS, reads proxied with the key ----

  api.post("/kanban/create_card", async (request, reply) => {
    const parsed = kanbanCreateCardSchema.safeParse(request.body);
    if (!parsed.success) {
      return reply.code(422).send({ error: parsed.error.issues[0]?.message ?? "inválido" });
    }
    if (!hub.connected) {
      return reply.code(503).send({ error: "Daemon desconectado do hub." });
    }
    const { board_id, ...rest } = parsed.data;
    hub.sendKanbanAction(board_id, "create_card", compact(rest));
    return { queued: true };
  });

  api.post("/kanban/move_card", async (request, reply) => {
    const parsed = kanbanMoveCardSchema.safeParse(request.body);
    if (!parsed.success) {
      return reply.code(422).send({ error: parsed.error.issues[0]?.message ?? "inválido" });
    }
    if (!hub.connected) {
      return reply.code(503).send({ error: "Daemon desconectado do hub." });
    }
    const { board_id, ...rest } = parsed.data;
    hub.sendKanbanAction(board_id, "move_card", compact(rest));
    return { queued: true };
  });

  api.post("/kanban/comment", async (request, reply) => {
    const parsed = kanbanCommentSchema.safeParse(request.body);
    if (!parsed.success) {
      return reply.code(422).send({ error: parsed.error.issues[0]?.message ?? "inválido" });
    }
    if (!hub.connected) {
      return reply.code(503).send({ error: "Daemon desconectado do hub." });
    }
    const { board_id, card_id, body } = parsed.data;
    hub.sendKanbanAction(board_id, "comment", { card_id, body });
    return { queued: true };
  });

  api.get("/kanban/boards", async (_request, reply) => {
    try {
      return await hub.kanbanGet("/api/kanban/agent/boards");
    } catch (error) {
      return reply.code(502).send({ error: error instanceof Error ? error.message : "falha" });
    }
  });

  api.get("/kanban/cards", async (request, reply) => {
    const query = request.query as { board?: string; mine?: string };
    const boardId = Number(query.board);
    if (!Number.isInteger(boardId) || boardId <= 0) {
      return reply.code(422).send({ error: "parâmetro 'board' (id) é obrigatório" });
    }
    const mine = query.mine === "true";
    try {
      return await hub.kanbanGet(`/api/kanban/agent/boards/${boardId}/full?mine=${mine}`);
    } catch (error) {
      return reply.code(502).send({ error: error instanceof Error ? error.message : "falha" });
    }
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
