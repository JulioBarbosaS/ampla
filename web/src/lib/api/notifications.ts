import { api } from "./client";
import type { AppNotification, NotificationPrefs, NotificationStatus, NotifyLevel } from "./types";

export interface NotificationPatch {
  unread?: boolean;
  status?: NotificationStatus;
}

export const notificationsApi = {
  list: (status?: NotificationStatus) =>
    api.get<AppNotification[]>(`/api/notifications${status ? `?status=${status}` : ""}`),
  unreadCount: () => api.get<{ unread_count: number }>("/api/notifications/unread-count"),
  triage: (id: number, patch: NotificationPatch) =>
    api.patch<AppNotification>(`/api/notifications/${id}`, patch),
  readAll: () => api.post<{ unread_count: number }>("/api/notifications/read-all", {}),
  getPrefs: () => api.get<NotificationPrefs>("/api/notifications/prefs"),
  setPrefs: (notify_level: NotifyLevel) =>
    api.patch<NotificationPrefs>("/api/notifications/prefs", { notify_level }),
};
