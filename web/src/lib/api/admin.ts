import { api } from "./client";
import type { KillSwitchState } from "./types";

/** Instance-wide admin controls (admin-only on the hub). */
export const adminApi = {
  getKillSwitch: () => api.get<KillSwitchState>("/api/admin/kill-switch"),
  setKillSwitch: (enabled: boolean) =>
    api.post<KillSwitchState>("/api/admin/kill-switch", { enabled }),
};
