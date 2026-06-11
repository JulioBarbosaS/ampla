import { create } from "zustand";
import type { AppNotification } from "../lib/api/types";

/**
 * Inbox view-state (Epic 02). `items` is the current filtered list; `unreadCount`
 * drives the topbar badge. Triage is applied optimistically by replacing the
 * patched row; WS deltas (slice b) will reuse `upsert`/`setUnreadCount`.
 */
interface InboxState {
  items: AppNotification[];
  unreadCount: number;
  setItems: (items: AppNotification[]) => void;
  setUnreadCount: (n: number) => void;
  /** Replace a row in place after a triage/delta (keeps list order). */
  patch: (item: AppNotification) => void;
}

export const useInboxStore = create<InboxState>()((set) => ({
  items: [],
  unreadCount: 0,
  setItems: (items) => set({ items }),
  setUnreadCount: (n) => set({ unreadCount: Math.max(0, n) }),
  patch: (item) => set((s) => ({ items: s.items.map((n) => (n.id === item.id ? item : n)) })),
}));
