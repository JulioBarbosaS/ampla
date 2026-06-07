import { api } from "./client";
import type { Group } from "./types";

export const groupsApi = {
  list: () => api.get<Group[]>("/api/groups"),
  create: (data: { slug: string; display_name: string }) => api.post<Group>("/api/groups", data),
  remove: (slug: string) => api.delete<void>(`/api/groups/${slug}`),
  addMember: (slug: string, agent: string) =>
    api.post<void>(`/api/groups/${slug}/members`, { agent }),
  removeMember: (slug: string, agent: string) =>
    api.delete<void>(`/api/groups/${slug}/members/${encodeURIComponent(agent)}`),
};
