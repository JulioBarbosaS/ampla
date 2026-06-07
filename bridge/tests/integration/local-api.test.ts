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

describe("API local do daemon (consumida pelo MCP)", () => {
  it("GET /status reflete conexão, settings e não lidas", async () => {
    const response = await daemon.api.inject({ method: "GET", url: "/status" });
    expect(response.statusCode).toBe(200);
    const body = response.json();
    expect(body.agent_id).toBe(AGENT);
    expect(body.connected).toBe(true);
    expect(body.settings.mode).toBe("inbox");
    expect(body.unread).toBe(0);
  });

  it("POST /send envia pelo WS e registra no histórico", async () => {
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

  it("POST /send valida payload (422) e exige conexão (503)", async () => {
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

  it("GET /inbox retorna não lidas e marca como lidas por padrão", async () => {
    hub.pushMessage(AGENT, wireMessage(21, "mobile-eduardo", AGENT, "primeira"));
    await waitFor(() => daemon.store.unreadCount() === 1, 5000, "mensagem na inbox");

    const first = await daemon.api.inject({ method: "GET", url: "/inbox" });
    expect(first.json().messages).toHaveLength(1);

    const second = await daemon.api.inject({ method: "GET", url: "/inbox" });
    expect(second.json().messages).toHaveLength(0); // já lidas
  });

  it("POST /send para @grupo envia o frame de broadcast", async () => {
    const response = await daemon.api.inject({
      method: "POST",
      url: "/send",
      payload: { to: "@frontend-team", body: "deploy às 18h", type: "notification" },
    });
    expect(response.statusCode).toBe(200);
    expect(response.json()).toMatchObject({ sent: true, broadcast: true });

    await waitFor(() => hub.sentMessages().length === 1, 5000, "frame no hub");
    expect(hub.sentMessages()[0]).toEqual({ to: "@frontend-team", body: "deploy às 18h" });
    // registrado no histórico local com a origem de grupo
    expect(daemon.store.conversation("@frontend-team")[0]?.group).toBe("@frontend-team");
  });

  it("GET /groups expõe os grupos recebidos no hello_ack", async () => {
    const response = await daemon.api.inject({ method: "GET", url: "/groups" });
    expect(response.statusCode).toBe(200);
    expect(response.json()).toEqual({ groups: [] });
  });

  it("GET /presence lista online; GET /partners lista interlocutores", async () => {
    const presence = await daemon.api.inject({ method: "GET", url: "/presence" });
    expect(presence.json().online).toContain(AGENT);

    hub.pushMessage(AGENT, wireMessage(22, "infra-maria", AGENT, "oi"));
    await waitFor(() => daemon.store.partners().length === 1, 5000, "partner registrado");
    const partners = await daemon.api.inject({ method: "GET", url: "/partners" });
    expect(partners.json().partners).toEqual(["infra-maria"]);
  });
});
