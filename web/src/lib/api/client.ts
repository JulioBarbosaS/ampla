/**
 * Single HTTP entry point to the hub (docs/ARCHITECTURE.md · web rules):
 * components never call fetch directly.
 */

import { useAuthStore } from "../../stores/auth";

// Always same origin: in prod the hub serves the built panel; in dev the Vite
// server proxies /api and /ws to the hub (see vite.config.ts). Same origin is
// required for the HttpOnly SameSite=Strict session cookie to travel at all.
// VITE_HUB_URL stays as an escape hatch but is not the cookie-auth path.
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
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE",
  path: string,
  body?: unknown,
): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    method,
    credentials: "include", // send the HttpOnly session cookie
    headers: {
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });

  if (response.status === 401) {
    useAuthStore.getState().clear(); // session expired → back to login
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
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  delete: <T>(path: string) => request<T>("DELETE", path),
};

export function wsUrl(): string {
  return `${BASE.replace(/^http/, "ws")}/ws`;
}
