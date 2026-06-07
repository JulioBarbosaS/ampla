import { create } from "zustand";
import type { DirectoryEntry, Group, Message } from "../lib/api/types";

/** Chave canônica de uma conversa (independe da direção). */
export function conversationKey(a: string, b: string): string {
  return [a, b].sort().join("|");
}

interface ChatState {
  /** Agente "meu" pelo qual o usuário conversa e enxerga a sidebar. */
  perspective: string | null;
  /** Parceiro selecionado na sidebar. */
  partner: string | null;
  directory: DirectoryEntry[];
  groups: Group[];
  online: Record<string, boolean>;
  conversations: Record<string, Message[]>;

  setPerspective: (slug: string | null) => void;
  setPartner: (slug: string | null) => void;
  setDirectory: (entries: DirectoryEntry[]) => void;
  setGroups: (groups: Group[]) => void;
  setOnlineList: (slugs: string[]) => void;
  setPresence: (slug: string, online: boolean) => void;
  setConversation: (a: string, b: string, messages: Message[]) => void;
  addMessage: (message: Message) => void;
}

export const useChatStore = create<ChatState>((set) => ({
  perspective: null,
  partner: null,
  directory: [],
  groups: [],
  online: {},
  conversations: {},

  setPerspective: (slug) => set({ perspective: slug, partner: null }),
  setPartner: (slug) => set({ partner: slug }),
  setGroups: (groups) => set({ groups }),
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
        // REST devolve mais recentes primeiro; UI lê em ordem cronológica
        [conversationKey(a, b)]: [...messages].sort((m1, m2) => m1.id - m2.id),
      },
    })),
  addMessage: (message) =>
    set((state) => {
      const key = conversationKey(message.from, message.to);
      const existing = state.conversations[key] ?? [];
      if (existing.some((m) => m.id === message.id)) {
        return state; // dedup (eco do próprio POST via observer)
      }
      return {
        conversations: { ...state.conversations, [key]: [...existing, message] },
      };
    }),
}));
