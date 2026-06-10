import { api } from "./client";
import type { Invite, TokenResponse, User } from "./types";

export const authApi = {
  setupStatus: () => api.get<{ needs_setup: boolean }>("/api/auth/setup-status"),
  setup: (data: { email: string; name: string; password: string }) =>
    api.post<TokenResponse>("/api/auth/setup", data),
  register: (data: { email: string; name: string; password: string; invite_code: string }) =>
    api.post<TokenResponse>("/api/auth/register", data),
  login: (data: { email: string; password: string }) =>
    api.post<TokenResponse>("/api/auth/login", data),
  logout: () => api.post<null>("/api/auth/logout"),
  me: () => api.get<User>("/api/auth/me"),
  updateProfile: (data: { name: string }) => api.patch<User>("/api/auth/me", data),
  changePassword: (data: { current_password: string; new_password: string }) =>
    api.post<null>("/api/auth/me/password", data),
  createInvite: () => api.post<Invite>("/api/invites"),
  listInvites: () => api.get<Invite[]>("/api/invites"),
};
