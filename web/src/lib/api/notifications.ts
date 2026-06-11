import { api } from "./client";
import type { AppNotification, NotificationStatus } from "./types";

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
};
