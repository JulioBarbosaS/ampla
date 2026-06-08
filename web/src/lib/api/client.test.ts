import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "../../stores/auth";
import { ApiError, api } from "./client";

const USER = {
  id: 1,
  email: "julio@example.com",
  name: "Julio",
  role: "admin" as const,
  created_at: "2026-06-06T12:00:00Z",
};

function mockFetch(status: number, payload: unknown) {
  const fn = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fn);
  return fn;
}

beforeEach(() => {
  useAuthStore.setState({ user: null });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api client", () => {
  it("sends the session cookie (credentials: include) and no Authorization header", async () => {
    const fetchMock = mockFetch(200, { ok: true });

    await api.get("/api/auth/me");

    const [, init] = fetchMock.mock.calls[0]!;
    expect((init as RequestInit).credentials).toBe("include");
    expect((init as RequestInit).headers).not.toHaveProperty("Authorization");
  });

  it("hub error becomes an ApiError with the detail", async () => {
    mockFetch(403, { code: "permission_denied", detail: "Você não gerencia este agente." });
    await expect(api.get("/api/agents/x")).rejects.toThrowError(
      new ApiError(403, "Você não gerencia este agente."),
    );
  });

  it("401 tears down the local session (the cookie is gone or expired)", async () => {
    useAuthStore.setState({ user: USER });
    mockFetch(401, { detail: "Sessão inválida ou expirada." });

    await expect(api.get("/api/auth/me")).rejects.toThrow();
    expect(useAuthStore.getState().user).toBeNull();
  });
});
