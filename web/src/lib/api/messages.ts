import { api } from "./client";
import type { ConversationPartner, Message } from "./types";

export const messagesApi = {
  conversation: (a: string, b: string, limit = 50) =>
    api.get<Message[]>(
      `/api/messages/conversation?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}&limit=${limit}`,
    ),
  partners: (agent: string) =>
    api.get<ConversationPartner[]>(`/api/messages/partners?agent=${encodeURIComponent(agent)}`),
  send: (from: string, to: string, body: string) =>
    api.post<Message>("/api/messages", { from, to, body }),
};
