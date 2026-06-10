/**
 * WebSocket protocol — MIRROR of hub/app/schemas/ws.py.
 * Changed it there, change it here IN THE SAME COMMIT (docs/ARCHITECTURE.md · WS Protocol).
 */

import { z } from "zod";

// ---------- agent settings (source of truth: hub) ----------

export const agentSettingsSchema = z.object({
  mode: z.enum(["inbox", "auto"]),
  allowed_senders: z.array(z.string()).nullable(),
  max_auto_per_hour: z.number().int(),
  auto_timeout_secs: z.number().int(),
  instructions: z.string(),
  // Auto-respond filesystem guardrails (the daemon turns these into claude -p
  // deny-rules/flags). trusted_senders bypass them with full access.
  allow_write: z.boolean(),
  block_hidden_files: z.boolean(),
  block_sensitive_paths: z.boolean(),
  confine_to_dir: z.boolean(),
  denied_paths: z.array(z.string()),
  trusted_senders: z.array(z.string()),
});
export type AgentSettings = z.infer<typeof agentSettingsSchema>;

// ---------- message as it travels (REST and WS) ----------

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
  group: z.string().nullable().default(null), // "@frontend-team"/"@all" in fan-out
  thread_id: z.number().int().nullable(),
  in_reply_to: z.number().int().nullable(),
  created_at: z.string(),
  delivered_at: z.string().nullable(),
  expires_at: z.string().nullable(),
});
export type WireMessage = z.infer<typeof wireMessageSchema>;

export const groupInfoSchema = z.object({
  slug: z.string(),
  display_name: z.string(),
  members: z.array(z.string()),
});
export type GroupInfo = z.infer<typeof groupInfoSchema>;

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

/** Receipt confirmation (at-least-once): sent by the daemon when it writes
 * the message; without it the hub resends on the next hello. Mirrors AckFrame. */
export interface AckFrame {
  type: "ack";
  message_id: number;
}

/** Reply to the hub's ping (heartbeat). Mirrors PongFrame. */
export interface PongFrame {
  type: "pong";
}

/** Auto-reply generation signal for the panel's "responding…" indicator.
 * Mirrors ActivityFrame. */
export interface ActivityFrame {
  type: "activity";
  state: "responding" | "idle";
}

export type ClientFrame = HelloFrame | SendMessageFrame | AckFrame | PongFrame | ActivityFrame;

// ---------- hub → daemon ----------

export const helloAckFrameSchema = z.object({
  type: z.literal("hello_ack"),
  agent_id: z.string().nullable(),
  online: z.array(z.string()),
  settings: agentSettingsSchema.nullable(),
  pending: z.array(wireMessageSchema),
  groups: z.array(groupInfoSchema).default([]),
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

export const agentActivityFrameSchema = z.object({
  type: z.literal("agent_activity"),
  agent_id: z.string(),
  state: z.enum(["responding", "idle"]),
});

export const settingsUpdateFrameSchema = z.object({
  type: z.literal("settings_update"),
  settings: agentSettingsSchema,
});

export const broadcastResultFrameSchema = z.object({
  type: z.literal("broadcast_result"),
  group: z.string(),
  sent: z.array(z.string()),
  skipped: z.array(z.string()),
  offline: z.array(z.string()),
});

export const errorFrameSchema = z.object({
  type: z.literal("error"),
  code: z.string(),
  detail: z.string(),
});

export const pingFrameSchema = z.object({
  type: z.literal("ping"),
});

export const serverFrameSchema = z.discriminatedUnion("type", [
  helloAckFrameSchema,
  messageDeliveryFrameSchema,
  deliveredFrameSchema,
  presenceFrameSchema,
  agentActivityFrameSchema,
  settingsUpdateFrameSchema,
  broadcastResultFrameSchema,
  errorFrameSchema,
  pingFrameSchema,
]);
export type ServerFrame = z.infer<typeof serverFrameSchema>;
export type HelloAckFrame = z.infer<typeof helloAckFrameSchema>;

/** Safe parse of a frame coming from the hub; null for an unknown/invalid frame. */
export function parseServerFrame(raw: string): ServerFrame | null {
  try {
    return serverFrameSchema.parse(JSON.parse(raw));
  } catch {
    return null;
  }
}
