import { create } from "zustand";
import type { DirectoryEntry, Group, Message } from "../lib/api/types";

/** Canonical key for a conversation (direction-independent). */
export function conversationKey(a: string, b: string): string {
  return [a, b].sort().join("|");
}

export interface MessageThread {
  root: Message;
  replies: Message[];
}

/**
 * Group a flat conversation into threads by `thread_id`. The root is the message
 * whose `id === thread_id`; everything else in the thread is an ordered reply.
 * Threads and replies are ordered by id (the store keeps messages in id order,
 * which is chronological).
 */
export function groupThreads(messages: Message[]): MessageThread[] {
  const byThread = new Map<number, Message[]>();
  for (const m of messages) {
    const tid = m.thread_id ?? m.id;
    const arr = byThread.get(tid);
    if (arr) arr.push(m);
    else byThread.set(tid, [m]);
  }
  const threads: MessageThread[] = [];
  for (const [tid, msgs] of byThread) {
    const sorted = [...msgs].sort((a, b) => a.id - b.id);
    const root = sorted.find((m) => m.id === tid) ?? sorted[0];
    threads.push({ root, replies: sorted.filter((m) => m.id !== root.id) });
  }
  return threads.sort((a, b) => a.root.id - b.root.id);
}

interface ChatState {
  /** The user's "own" agent through which they chat and view the sidebar. */
  perspective: string | null;
  /** Partner selected in the sidebar. */
  partner: string | null;
  directory: DirectoryEntry[];
  groups: Group[];
  online: Record<string, boolean>;
  conversations: Record<string, Message[]>;
  /** Panel WS connection (for the "reconectando…" indicator). */
  wsConnected: boolean;

  setPerspective: (slug: string | null) => void;
  setPartner: (slug: string | null) => void;
  setDirectory: (entries: DirectoryEntry[]) => void;
  setGroups: (groups: Group[]) => void;
  setWsConnected: (connected: boolean) => void;
  setOnlineList: (slugs: string[]) => void;
  setPresence: (slug: string, online: boolean) => void;
  setConversation: (a: string, b: string, messages: Message[]) => void;
  addMessage: (message: Message) => void;
  markDelivered: (messageId: number) => void;
}

export const useChatStore = create<ChatState>((set) => ({
  perspective: null,
  partner: null,
  directory: [],
  groups: [],
  online: {},
  conversations: {},
  wsConnected: true,

  setPerspective: (slug) => set({ perspective: slug, partner: null }),
  setPartner: (slug) => set({ partner: slug }),
  setGroups: (groups) => set({ groups }),
  setWsConnected: (connected) => set({ wsConnected: connected }),
  setDirectory: (entries) =>
    set((state) => ({
      directory: entries,
      online: {
        ...Object.fromEntries(entries.map((e) => [e.slug, e.online])),
        ...state.online,
      },
    })),
  setOnlineList: (slugs) =>
    set((state) => ({
      online: {
        ...Object.fromEntries(Object.keys(state.online).map((k) => [k, false])),
        ...Object.fromEntries(slugs.map((s) => [s, true])),
      },
    })),
  setPresence: (slug, online) => set((state) => ({ online: { ...state.online, [slug]: online } })),
  setConversation: (a, b, messages) =>
    set((state) => ({
      conversations: {
        ...state.conversations,
        // REST returns newest first; UI reads in chronological order
        [conversationKey(a, b)]: [...messages].sort((m1, m2) => m1.id - m2.id),
      },
    })),
  addMessage: (message) =>
    set((state) => {
      const key = conversationKey(message.from, message.to);
      const existing = state.conversations[key] ?? [];
      if (existing.some((m) => m.id === message.id)) {
        return state; // dedup (echo of our own POST via observer)
      }
      return {
        conversations: { ...state.conversations, [key]: [...existing, message] },
      };
    }),
  markDelivered: (messageId) =>
    set((state) => {
      // The `delivered` frame arrives after the bubble (which entered with a
      // null delivered_at on dispatch). Find the message in the conversation
      // and stamp the delivery.
      for (const [key, messages] of Object.entries(state.conversations)) {
        const idx = messages.findIndex((m) => m.id === messageId);
        if (idx === -1) continue;
        if (messages[idx].delivered_at) return state; // already stamped
        const updated = [...messages];
        updated[idx] = { ...updated[idx], delivered_at: new Date().toISOString() };
        return { conversations: { ...state.conversations, [key]: updated } };
      }
      return state;
    }),
}));
