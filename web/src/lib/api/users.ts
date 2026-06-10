import { api } from "./client";
import type { User } from "./types";

export const usersApi = {
  list: () => api.get<User[]>("/api/users"),
  setRole: (userId: number, role: "admin" | "member") =>
    api.patch<User>(`/api/users/${userId}/role`, { role }),
  issuePasswordReset: (userId: number) =>
    api.post<{ token: string; expires_at: string }>(`/api/users/${userId}/password-reset`),
};
