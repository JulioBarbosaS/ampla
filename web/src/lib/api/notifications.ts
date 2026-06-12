import { api } from "./client";
import type {
  AppNotification,
  NotificationPrefs,
  NotificationStatus,
  NotificationSubscription,
  NotifyLevel,
  SubscriptionState,
} from "./types";

export interface NotificationPatch {
  unread?: boolean;
  status?: NotificationStatus;
}

/** Canned-view filter (server-side query). Built-in views map onto these. */
export interface NotificationFilter {
  status?: NotificationStatus;
  reason?: string;
}

export const notificationsApi = {
  list: (filter?: NotificationFilter) => {
    const params = new URLSearchParams();
    if (filter?.status) params.set("status", filter.status);
    if (filter?.reason) params.set("reason", filter.reason);
    const qs = params.toString();
    return api.get<AppNotification[]>(`/api/notifications${qs ? `?${qs}` : ""}`);
  },
  unreadCount: () => api.get<{ unread_count: number }>("/api/notifications/unread-count"),
  triage: (id: number, patch: NotificationPatch) =>
    api.patch<AppNotification>(`/api/notifications/${id}`, patch),
  readAll: () => api.post<{ unread_count: number }>("/api/notifications/read-all", {}),
  getPrefs: () => api.get<NotificationPrefs>("/api/notifications/prefs"),
  setPrefs: (notify_level: NotifyLevel) =>
    api.patch<NotificationPrefs>("/api/notifications/prefs", { notify_level }),
  subscribe: (subject_key: string, state: SubscriptionState) =>
    api.put<NotificationSubscription>("/api/notifications/subscription", { subject_key, state }),
};
