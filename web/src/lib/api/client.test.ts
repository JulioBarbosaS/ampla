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
  useAuthStore.setState({ token: null, user: null });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api client", () => {
  it("sends Authorization when a token is present", async () => {
    useAuthStore.setState({ token: "jwt-token", user: USER });
    const fetchMock = mockFetch(200, { ok: true });

    await api.get("/api/auth/me");

    const [, init] = fetchMock.mock.calls[0]!;
    expect((init as RequestInit).headers).toMatchObject({
      Authorization: "Bearer jwt-token",
    });
  });

  it("hub error becomes an ApiError with the detail", async () => {
    mockFetch(403, { code: "permission_denied", detail: "Você não gerencia este agente." });
    await expect(api.get("/api/agents/x")).rejects.toThrowError(
      new ApiError(403, "Você não gerencia este agente."),
    );
  });

  it("401 with a token tears down the session (automatic logout)", async () => {
    useAuthStore.setState({ token: "expirado", user: USER });
    mockFetch(401, { detail: "Sessão inválida ou expirada." });

    await expect(api.get("/api/auth/me")).rejects.toThrow();
    expect(useAuthStore.getState().token).toBeNull();
  });
});
