/**
 * Single HTTP entry point to the hub (docs/ARCHITECTURE.md · web rules):
 * components never call fetch directly.
 */

import { useAuthStore } from "../../stores/auth";

// Default to the same origin the panel is served from — correct when the hub
// serves the built panel (Docker/one-URL install). In dev (panel on :5173,
// hub on :8000) set VITE_HUB_URL=http://localhost:8000.
const BASE = import.meta.env.VITE_HUB_URL ?? window.location.origin;

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(
  method: "GET" | "POST" | "PATCH" | "DELETE",
  path: string,
  body?: unknown,
): Promise<T> {
  const token = useAuthStore.getState().token;
  const response = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });

  if (response.status === 401 && token) {
    useAuthStore.getState().logout(); // session expired → back to login
  }
  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? typeof payload.detail === "string"
          ? payload.detail
          : "Dados inválidos."
        : `Erro ${response.status}`;
    throw new ApiError(response.status, detail);
  }
  return payload as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  delete: <T>(path: string) => request<T>("DELETE", path),
};

export function wsUrl(): string {
  return `${BASE.replace(/^http/, "ws")}/ws`;
}
