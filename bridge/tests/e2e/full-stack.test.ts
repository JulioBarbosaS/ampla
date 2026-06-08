/**
 * REAL end-to-end integration: hub (uvicorn + SQLite) ↔ two daemons.
 *
 * Validates the full product flow: admin setup via REST, keys,
 * hello/ack, real-time routing, inbox, settings_update push,
 * auto-respond (fake runner) and the [auto] prefix anti-loop.
 *
 * Requires the hub venv (hub/.venv) — the suite is skipped if it does not exist.
 */

import { type ChildProcess, spawn } from "node:child_process";
import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { AUTO_REPLY_PREFIX, createDaemon, type Daemon } from "../../src/daemon/index.js";
import { waitFor } from "../integration/fake-hub.js";

const HUB_DIR = resolve(import.meta.dirname, "../../../hub");
const PYTHON = join(HUB_DIR, ".venv/bin/python");

/** Ephemeral port: avoids flakiness from conflict/TIME_WAIT of a fixed port. */
function getFreePort(): Promise<number> {
  return new Promise((resolvePort, reject) => {
    const server = createServer();
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (address === null || typeof address === "string") {
        reject(new Error("sem porta"));
        return;
      }
      const { port } = address;
      server.close(() => resolvePort(port));
    });
    server.on("error", reject);
  });
}

const hasHub = existsSync(PYTHON);

describe.skipIf(!hasHub)("full-stack: real hub ↔ real daemons", () => {
  let hubProcess: ChildProcess;
  let dir: string;
  let token = "";
  let daemonA: Daemon | null = null;
  let daemonB: Daemon | null = null;
  let healthy = false;
  let PORT = 0;
  let BASE = "";

  async function api(method: string, path: string, body?: unknown): Promise<any> {
    const response = await fetch(`${BASE}${path}`, {
      method,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    });
    if (!response.ok) {
      throw new Error(`${method} ${path} → ${response.status}: ${await response.text()}`);
    }
    return response.json();
  }

  beforeAll(async () => {
    PORT = await getFreePort();
    BASE = `http://127.0.0.1:${PORT}`;
    dir = mkdtempSync(join(tmpdir(), "amp-fullstack-"));
    hubProcess = spawn(PYTHON, ["-m", "uvicorn", "app.main:app", "--port", String(PORT)], {
      cwd: HUB_DIR,
      env: {
        ...process.env,
        AMP_DATABASE_URL: `sqlite+aiosqlite:///${join(dir, "hub.db")}`,
        AMP_JWT_SECRET: "fullstack-secret-com-32-bytes-ok!!",
      },
      stdio: "ignore",
    });
    // wait for the hub to respond
    await waitFor(
      () => {
        void fetch(`${BASE}/api/health`)
          .then((r) => {
            healthy = r.ok;
          })
          .catch(() => {});
        return healthy;
      },
      15_000,
      "hub de pé",
    );

    // team setup: admin + 2 agents + keys
    token = (
      await api("POST", "/api/auth/setup", {
        email: "admin@example.com",
        name: "Admin",
        password: "senha-muito-segura-1",
      })
    ).token;
    await api("POST", "/api/agents", { slug: "backend-julio", display_name: "Backend" });
    await api("POST", "/api/agents", { slug: "mobile-eduardo", display_name: "Mobile" });
    const keyA = (await api("POST", "/api/agents/backend-julio/keys", { label: "e2e" })).key;
    const keyB = (await api("POST", "/api/agents/mobile-eduardo/keys", { label: "e2e" })).key;

    // two real daemons; B's uses a fake "claude" that replies on the spot
    const runnerB = vi.fn().mockResolvedValue("Sim: POST /api/v1/auth/password-reset (auth.py:42)");
    daemonA = createDaemon(
      {
        hub_url: `ws://127.0.0.1:${PORT}/ws`,
        agent_id: "backend-julio",
        agent_key: keyA,
        claude_bin: "claude",
      },
      { store: join(dir, "store-a.jsonl") },
    );
    daemonB = createDaemon(
      {
        hub_url: `ws://127.0.0.1:${PORT}/ws`,
        agent_id: "mobile-eduardo",
        agent_key: keyB,
        claude_bin: "claude",
      },
      { store: join(dir, "store-b.jsonl") },
      runnerB,
    );
    daemonA.hub.start();
    daemonB.hub.start();
    await waitFor(
      () => daemonA!.hub.connected && daemonB!.hub.connected,
      10_000,
      "daemons conectados",
    );
  }, 60_000);

  afterAll(async () => {
    await daemonA?.shutdown();
    await daemonB?.shutdown();
    hubProcess?.kill("SIGKILL");
    rmSync(dir, { recursive: true, force: true });
  });

  it("presence: each daemon sees the other online", async () => {
    await waitFor(
      () => daemonA!.hub.onlineAgents().includes("mobile-eduardo"),
      5_000,
      "B online para A",
    );
    expect(daemonB!.hub.onlineAgents()).toContain("backend-julio");
  });

  it("a real-time routed message lands in the recipient's inbox", async () => {
    const response = await daemonA!.api.inject({
      method: "POST",
      url: "/send",
      payload: { to: "mobile-eduardo", body: "Tem release hoje?" },
    });
    expect(response.statusCode).toBe(200);
    await waitFor(() => daemonB!.store.unreadCount() === 1, 5_000, "inbox de B");
    expect(daemonB!.store.inbox(true)[0]?.body).toBe("Tem release hoje?");
  });

  it("a PATCH from the panel arrives as settings_update and enables auto-respond", async () => {
    // B starts in inbox (safe default) — panel switches to auto
    await api("PATCH", "/api/agents/mobile-eduardo/settings", { mode: "auto" });
    await waitFor(() => daemonB!.hub.settings?.mode === "auto", 5_000, "settings push");

    await daemonA!.api.inject({
      method: "POST",
      url: "/send",
      payload: { to: "mobile-eduardo", body: "Existe endpoint de reset de senha?" },
    });

    // B's automatic reply arrives in A's inbox/history
    await waitFor(
      () =>
        daemonA!.store
          .conversation("mobile-eduardo")
          .some((m) => m.direction === "in" && m.body.startsWith(AUTO_REPLY_PREFIX)),
      10_000,
      "auto-resposta em A",
    );
    const reply = daemonA!.store
      .conversation("mobile-eduardo")
      .find((m) => m.body.startsWith(AUTO_REPLY_PREFIX))!;
    expect(reply.body).toContain("password-reset");
  });

  it("anti-loop: A (auto) does not reply to B's [auto] reply", async () => {
    await api("PATCH", "/api/agents/backend-julio/settings", { mode: "auto" });
    await waitFor(() => daemonA!.hub.settings?.mode === "auto", 5_000, "A em modo auto");

    const sentBefore = daemonA!.store
      .conversation("mobile-eduardo")
      .filter((m) => m.direction === "out").length;

    // there is already an [auto] in A's inbox (previous test) — nothing new should go out
    await new Promise((resolve) => setTimeout(resolve, 300));
    const sentAfter = daemonA!.store
      .conversation("mobile-eduardo")
      .filter((m) => m.direction === "out").length;
    expect(sentAfter).toBe(sentBefore);
  });

  it("history in the hub matches the flow (REST)", async () => {
    const messages = await api(
      "GET",
      "/api/messages/conversation?a=backend-julio&b=mobile-eduardo&limit=50",
    );
    const bodies = messages.map((m: { body: string }) => m.body);
    expect(bodies.some((b: string) => b.includes("reset de senha"))).toBe(true);
    expect(bodies.some((b: string) => b.startsWith(AUTO_REPLY_PREFIX))).toBe(true);
    // everything delivered (both online)
    expect(messages.every((m: { delivered_at: string | null }) => m.delivered_at !== null)).toBe(
      true,
    );
  });
});
