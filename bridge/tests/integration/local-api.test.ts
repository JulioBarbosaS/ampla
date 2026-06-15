import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { createDaemon, type Daemon } from "../../src/daemon/index.js";
import { FakeHub, waitFor, wireMessage } from "./fake-hub.js";

const AGENT = "backend-julio";
const KEY = `amp_${"cd".repeat(32)}`;

let hub: FakeHub;
let daemon: Daemon;
let dir: string;

beforeEach(async () => {
  hub = new FakeHub();
  hub.validKeys.set(AGENT, KEY);
  dir = mkdtempSync(join(tmpdir(), "amp-api-"));
  const url = await hub.start();
  daemon = createDaemon(
    { hub_url: url, agent_id: AGENT, agent_key: KEY, claude_bin: "claude" },
    { store: join(dir, "messages.jsonl") },
  );
  daemon.hub.start();
  await waitFor(() => daemon.hub.connected, 5000, "conexão com o hub");
});

afterEach(async () => {
  await daemon.shutdown();
  await hub.stop();
  rmSync(dir, { recursive: true, force: true });
});

describe("daemon local API (consumed by the MCP)", () => {
  it("GET /status reflects connection, settings and unread count", async () => {
    const response = await daemon.api.inject({ method: "GET", url: "/status" });
    expect(response.statusCode).toBe(200);
    const body = response.json();
    expect(body.agent_id).toBe(AGENT);
    expect(body.connected).toBe(true);
    expect(body.settings.mode).toBe("inbox");
    expect(body.unread).toBe(0);
  });

  it("POST /send sends over the WS and records in the history", async () => {
    const response = await daemon.api.inject({
      method: "POST",
      url: "/send",
      payload: { to: "mobile-eduardo", body: "Confere o endpoint X?" },
    });
    expect(response.statusCode).toBe(200);
    expect(response.json().sent).toBe(true);

    await waitFor(() => hub.sentMessages().length === 1, 5000, "frame no hub");
    expect(hub.sentMessages()[0]).toEqual({ to: "mobile-eduardo", body: "Confere o endpoint X?" });

    const history = await daemon.api.inject({
      method: "GET",
      url: "/history?with=mobile-eduardo",
    });
    expect(history.json().messages).toHaveLength(1);
  });

  it("POST /send validates the payload (422) and requires a connection (503)", async () => {
    const invalid = await daemon.api.inject({
      method: "POST",
      url: "/send",
      payload: { to: "x", body: "" },
    });
    expect(invalid.statusCode).toBe(422);

    daemon.hub.stop();
    await waitFor(() => !daemon.hub.connected, 5000, "desconexão");
    const offline = await daemon.api.inject({
      method: "POST",
      url: "/send",
      payload: { to: "mobile-eduardo", body: "olá" },
    });
    expect(offline.statusCode).toBe(503);
  });

  it("POST /delegate sends a delegate frame and records the task locally", async () => {
    const response = await daemon.api.inject({
      method: "POST",
      url: "/delegate",
      payload: { to: "mobile-eduardo", task: "Revisar o login", context: "ver auth.py" },
    });
    expect(response.statusCode).toBe(200);
    expect(response.json()).toMatchObject({ delegated: true, to: "mobile-eduardo" });

    await waitFor(() => hub.sentDelegations().length === 1, 5000, "frame de delegação no hub");
    expect(hub.sentDelegations()[0]).toEqual({
      to: "mobile-eduardo",
      task: "Revisar o login",
      context: "ver auth.py",
    });
    // the outgoing task is mirrored into the local history (task + context)
    const history = await daemon.api.inject({
      method: "GET",
      url: "/history?with=mobile-eduardo",
    });
    expect(history.json().messages).toHaveLength(1);
    expect(history.json().messages[0].type).toBe("task");
  });

  it("POST /delegate rejects a group target and self-delegation (422)", async () => {
    const group = await daemon.api.inject({
      method: "POST",
      url: "/delegate",
      payload: { to: "@frontend-team", task: "x" },
    });
    expect(group.statusCode).toBe(422);

    const toSelf = await daemon.api.inject({
      method: "POST",
      url: "/delegate",
      payload: { to: AGENT, task: "x" },
    });
    expect(toSelf.statusCode).toBe(422);
  });

  it("GET /inbox returns unread messages and marks them read by default", async () => {
    hub.pushMessage(AGENT, wireMessage(21, "mobile-eduardo", AGENT, "primeira"));
    await waitFor(() => daemon.store.unreadCount() === 1, 5000, "mensagem na inbox");

    const first = await daemon.api.inject({ method: "GET", url: "/inbox" });
    expect(first.json().messages).toHaveLength(1);

    const second = await daemon.api.inject({ method: "GET", url: "/inbox" });
    expect(second.json().messages).toHaveLength(0); // already read
  });

  it("POST /send to @group sends the broadcast frame", async () => {
    const response = await daemon.api.inject({
      method: "POST",
      url: "/send",
      payload: { to: "@frontend-team", body: "deploy às 18h", type: "notification" },
    });
    expect(response.statusCode).toBe(200);
    expect(response.json()).toMatchObject({ sent: true, broadcast: true });

    await waitFor(() => hub.sentMessages().length === 1, 5000, "frame no hub");
    expect(hub.sentMessages()[0]).toEqual({ to: "@frontend-team", body: "deploy às 18h" });
    // recorded in the local history with the group origin
    expect(daemon.store.conversation("@frontend-team")[0]?.group).toBe("@frontend-team");
  });

  it("GET /groups exposes the groups received in the hello_ack", async () => {
    const response = await daemon.api.inject({ method: "GET", url: "/groups" });
    expect(response.statusCode).toBe(200);
    expect(response.json()).toEqual({ groups: [] });
  });

  it("GET /presence lists online agents; GET /partners lists interlocutors", async () => {
    const presence = await daemon.api.inject({ method: "GET", url: "/presence" });
    expect(presence.json().online).toContain(AGENT);

    hub.pushMessage(AGENT, wireMessage(22, "infra-maria", AGENT, "oi"));
    await waitFor(() => daemon.store.partners().length === 1, 5000, "partner registrado");
    const partners = await daemon.api.inject({ method: "GET", url: "/partners" });
    expect(partners.json().partners).toEqual(["infra-maria"]);
  });
});
