import { afterEach, describe, expect, it, vi } from "vitest";
import { groupsApi } from "./groups";
import { usersApi } from "./users";

/** Captures method + URL of the last fetch call (response always 200). */
function spyFetch(payload: unknown = {}) {
  const fn = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(payload), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fn);
  return fn;
}

function call(fetchMock: ReturnType<typeof spyFetch>) {
  const [url, init] = fetchMock.mock.calls[0]!;
  return { url: String(url), method: (init as RequestInit).method };
}

afterEach(() => vi.unstubAllGlobals());

describe("groupsApi", () => {
  it("list → GET /api/groups", async () => {
    const f = spyFetch([]);
    await groupsApi.list();
    expect(call(f)).toEqual({ url: expect.stringContaining("/api/groups"), method: "GET" });
  });

  it("create → POST /api/groups with slug and name", async () => {
    const f = spyFetch({});
    await groupsApi.create({ slug: "frontend-team", display_name: "Frontend" });
    const { url, method } = call(f);
    expect(method).toBe("POST");
    expect(url).toContain("/api/groups");
    expect(JSON.parse((f.mock.calls[0]![1] as RequestInit).body as string)).toEqual({
      slug: "frontend-team",
      display_name: "Frontend",
    });
  });

  it("remove → DELETE /api/groups/{slug}", async () => {
    const f = spyFetch({});
    await groupsApi.remove("frontend-team");
    expect(call(f)).toEqual({
      url: expect.stringContaining("/api/groups/frontend-team"),
      method: "DELETE",
    });
  });

  it("addMember → POST /api/groups/{slug}/members with agent", async () => {
    const f = spyFetch({});
    await groupsApi.addMember("frontend-team", "mobile-eduardo");
    const { url, method } = call(f);
    expect(method).toBe("POST");
    expect(url).toContain("/api/groups/frontend-team/members");
    expect(JSON.parse((f.mock.calls[0]![1] as RequestInit).body as string)).toEqual({
      agent: "mobile-eduardo",
    });
  });

  it("removeMember → DELETE /api/groups/{slug}/members/{agent}", async () => {
    const f = spyFetch({});
    await groupsApi.removeMember("frontend-team", "mobile-eduardo");
    expect(call(f)).toEqual({
      url: expect.stringContaining("/api/groups/frontend-team/members/mobile-eduardo"),
      method: "DELETE",
    });
  });
});

describe("usersApi", () => {
  it("list → GET /api/users", async () => {
    const f = spyFetch([]);
    await usersApi.list();
    expect(call(f)).toEqual({ url: expect.stringContaining("/api/users"), method: "GET" });
  });

  it("setRole → PATCH /api/users/{id}/role with role", async () => {
    const f = spyFetch({});
    await usersApi.setRole(7, "admin");
    const { url, method } = call(f);
    expect(method).toBe("PATCH");
    expect(url).toContain("/api/users/7/role");
    expect(JSON.parse((f.mock.calls[0]![1] as RequestInit).body as string)).toEqual({
      role: "admin",
    });
  });
});
