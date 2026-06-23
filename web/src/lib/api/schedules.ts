import { api } from "./client";
import type { ScheduledTask, ScheduleKind } from "./types";

/** Scheduled agent tasks (Epic 08). The hub validates (kind, spec) and enforces
 * ownership; the panel never touches the engine directly. */
export interface ScheduleInput {
  name: string;
  kind: ScheduleKind;
  spec: string;
  prompt: string;
  tools?: "read" | "write";
  enabled?: boolean;
}

export const schedulesApi = {
  list: (agentSlug: string) => api.get<ScheduledTask[]>(`/api/agents/${agentSlug}/schedules`),
  create: (agentSlug: string, data: ScheduleInput) =>
    api.post<ScheduledTask>(`/api/agents/${agentSlug}/schedules`, data),
  update: (scheduleId: number, data: Partial<ScheduleInput>) =>
    api.patch<ScheduledTask>(`/api/schedules/${scheduleId}`, data),
  remove: (scheduleId: number) => api.delete<void>(`/api/schedules/${scheduleId}`),
  runNow: (scheduleId: number) => api.post<ScheduledTask>(`/api/schedules/${scheduleId}/run`, {}),
};
