import { create } from "zustand";
import type { AppNotification } from "../lib/api/types";

/**
 * Inbox view-state (Epic 02). `items` is the current filtered list; `unreadCount`
 * drives the topbar badge. Triage replaces the patched row; live WS deltas
 * (slice b) feed `upsert` (a new/collapsed notification arrived) and `markRead`
 * (read-state synced from another tab).
 */
interface InboxState {
  items: AppNotification[];
  unreadCount: number;
  setItems: (items: AppNotification[]) => void;
  setUnreadCount: (n: number) => void;
  /** Replace a row in place after a triage/delta (keeps list order). */
  patch: (item: AppNotification) => void;
  /** Insert a freshly-arrived notification, or replace it if already listed. */
  upsert: (item: AppNotification) => void;
  /** Mark the given ids (or all) as read in the current list. */
  markRead: (ids: number[] | "all") => void;
}

export const useInboxStore = create<InboxState>()((set) => ({
  items: [],
  unreadCount: 0,
  setItems: (items) => set({ items }),
  setUnreadCount: (n) => set({ unreadCount: Math.max(0, n) }),
  patch: (item) => set((s) => ({ items: s.items.map((n) => (n.id === item.id ? item : n)) })),
  upsert: (item) =>
    set((s) =>
      s.items.some((n) => n.id === item.id)
        ? { items: s.items.map((n) => (n.id === item.id ? item : n)) }
        : { items: [item, ...s.items] },
    ),
  markRead: (ids) =>
    set((s) => ({
      items: s.items.map((n) =>
        ids === "all" || ids.includes(n.id) ? { ...n, unread: false } : n,
      ),
    })),
}));
