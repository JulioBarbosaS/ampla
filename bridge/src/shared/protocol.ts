/**
 * Protocolo WebSocket — ESPELHO de hub/app/schemas/ws.py.
 * Alterou lá, altera aqui NO MESMO COMMIT (docs/ARCHITECTURE.md · Protocolo WS).
 */

import { z } from "zod";

// ---------- settings do agente (fonte de verdade: hub) ----------

export const agentSettingsSchema = z.object({
  mode: z.enum(["inbox", "auto"]),
  allowed_senders: z.array(z.string()).nullable(),
  max_auto_per_hour: z.number().int(),
  auto_timeout_secs: z.number().int(),
  instructions: z.string(),
});
export type AgentSettings = z.infer<typeof agentSettingsSchema>;

// ---------- mensagem como trafega (REST e WS) ----------

export const messageTypeSchema = z.enum([
  "request",
  "response",
  "notification",
  "task",
  "alert",
  "status",
  "ack",
]);
export type MessageType = z.infer<typeof messageTypeSchema>;

export const prioritySchema = z.enum(["urgent", "high", "normal", "low"]);
export type Priority = z.infer<typeof prioritySchema>;

export const wireMessageSchema = z.object({
  id: z.number().int(),
  from: z.string(),
  to: z.string(),
  body: z.string(),
  type: messageTypeSchema,
  priority: prioritySchema,
  thread_id: z.number().int().nullable(),
  in_reply_to: z.number().int().nullable(),
  created_at: z.string(),
  delivered_at: z.string().nullable(),
  expires_at: z.string().nullable(),
});
export type WireMessage = z.infer<typeof wireMessageSchema>;

// ---------- daemon → hub ----------

export interface HelloFrame {
  type: "hello";
  agent_id: string;
  key: string;
}

export interface SendMessageFrame {
  type: "message";
  to: string;
  body: string;
  msg_type?: MessageType;
  priority?: Priority;
  in_reply_to?: number;
}

export type ClientFrame = HelloFrame | SendMessageFrame;

// ---------- hub → daemon ----------

export const helloAckFrameSchema = z.object({
  type: z.literal("hello_ack"),
  agent_id: z.string().nullable(),
  online: z.array(z.string()),
  settings: agentSettingsSchema.nullable(),
  pending: z.array(wireMessageSchema),
});

export const messageDeliveryFrameSchema = z.object({
  type: z.literal("message"),
  message: wireMessageSchema,
});

export const deliveredFrameSchema = z.object({
  type: z.literal("delivered"),
  message_id: z.number().int(),
  to: z.string(),
});

export const presenceFrameSchema = z.object({
  type: z.literal("presence"),
  agent_id: z.string(),
  status: z.enum(["online", "offline"]),
});

export const settingsUpdateFrameSchema = z.object({
  type: z.literal("settings_update"),
  settings: agentSettingsSchema,
});

export const errorFrameSchema = z.object({
  type: z.literal("error"),
  code: z.string(),
  detail: z.string(),
});

export const serverFrameSchema = z.discriminatedUnion("type", [
  helloAckFrameSchema,
  messageDeliveryFrameSchema,
  deliveredFrameSchema,
  presenceFrameSchema,
  settingsUpdateFrameSchema,
  errorFrameSchema,
]);
export type ServerFrame = z.infer<typeof serverFrameSchema>;
export type HelloAckFrame = z.infer<typeof helloAckFrameSchema>;

/** Parse seguro de frame vindo do hub; null para frame desconhecido/inválido. */
export function parseServerFrame(raw: string): ServerFrame | null {
  try {
    return serverFrameSchema.parse(JSON.parse(raw));
  } catch {
    return null;
  }
}
