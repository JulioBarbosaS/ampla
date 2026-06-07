import { api } from "./client";
import type { ConversationPartner, Message, MessageType, Priority } from "./types";

export interface SendOptions {
  type?: MessageType;
  priority?: Priority;
  in_reply_to?: number;
}

export interface BroadcastResult {
  group: string;
  sent: string[];
  skipped: string[];
  message_ids: number[];
}

export const messagesApi = {
  conversation: (a: string, b: string, limit = 50) =>
    api.get<Message[]>(
      `/api/messages/conversation?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}&limit=${limit}`,
    ),
  partners: (agent: string) =>
    api.get<ConversationPartner[]>(`/api/messages/partners?agent=${encodeURIComponent(agent)}`),
  send: (from: string, to: string, body: string, opts: SendOptions = {}) =>
    api.post<Message>("/api/messages", { from, to, body, ...opts }),
  broadcast: (from: string, group: string, body: string, opts: SendOptions = {}) =>
    api.post<BroadcastResult>("/api/messages/broadcast", { from, group, body, ...opts }),
};
