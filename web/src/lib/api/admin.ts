import { api } from "./client";
import type { AutorespondRun, KillSwitchState } from "./types";

/** Instance-wide admin controls (admin-only on the hub). */
export const adminApi = {
  getKillSwitch: () => api.get<KillSwitchState>("/api/admin/kill-switch"),
  setKillSwitch: (enabled: boolean) =>
    api.post<KillSwitchState>("/api/admin/kill-switch", { enabled }),
  // Instance-wide auto-respond transcript across every agent (admin oversight).
  autorespondRuns: (limit = 50) =>
    api.get<AutorespondRun[]>(`/api/admin/autorespond-runs?limit=${limit}`),
};
