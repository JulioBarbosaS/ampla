/**
 * Smoke da casca MCP: conecta um cliente MCP REAL (protocolo MCP, via
 * transporte em memória) ao servidor `buildServer()` e exercita as tools
 * amp_* contra um daemon vivo (unix socket) ligado a um hub fake.
 *
 * Fecha a lacuna do PLAN-onboarding-smoke: até aqui só a local-api do daemon
 * tinha teste; a camada MCP (tools/list, tools/call → socket → hub) nunca
 * fora exercitada. Não usa o `claude` real — valida a casca, não a conta.
 */

import { existsSync, mkdtempSync, rmSync, unlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { createDaemon, type Daemon } from "../../src/daemon/index.js";
import { FakeHub, waitFor, wireMessage } from "./fake-hub.js";

const AGENT = "backend-julio";
const PEER = "mobile-eduardo";
const KEY = `amp_${"ab".repeat(32)}`;

let dir: string;
let hub: FakeHub;
let daemon: Daemon;
let server: McpServer;
let client: Client;

/** Lê o JSON que a tool devolve como texto (asText: JSON.stringify). */
function payload(result: { content: Array<{ type: string; text?: string }> }): unknown {
  const text = result.content.find((c) => c.type === "text")?.text ?? "{}";
  return JSON.parse(text);
}

beforeAll(async () => {
  dir = mkdtempSync(join(tmpdir(), "amp-mcp-"));
  // AMP_HOME precisa estar setado ANTES de importar o módulo MCP: o
  // DaemonClient singleton resolve o socketPath() no carregamento.
  process.env.AMP_HOME = dir;

  const { socketPath, storePath } = await import("../../src/shared/config.js");

  hub = new FakeHub();
  hub.validKeys.set(AGENT, KEY);
  hub.pending = [wireMessage(1, PEER, AGENT, "tem reset de senha?")];
  const url = await hub.start();

  daemon = createDaemon(
    { hub_url: url, agent_id: AGENT, agent_key: KEY, claude_bin: "claude" },
    { store: storePath() },
  );
  const sock = socketPath();
  if (existsSync(sock)) unlinkSync(sock);
  await daemon.api.listen({ path: sock });
  daemon.hub.start();
  await waitFor(() => daemon.hub.connected, 5000, "daemon conectado ao hub");

  // Servidor MCP real + cliente MCP real, ligados por transporte em memória.
  const { buildServer } = await import("../../src/mcp/index.js");
  server = buildServer();
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  client = new Client({ name: "smoke-client", version: "0.0.0" });
  await Promise.all([server.connect(serverTransport), client.connect(clientTransport)]);
});

afterAll(async () => {
  await client?.close();
  await server?.close();
  await daemon?.shutdown();
  await hub?.stop();
  rmSync(dir, { recursive: true, force: true });
  process.env.AMP_HOME = undefined;
});

describe("smoke MCP: cliente real ↔ servidor real ↔ daemon", () => {
  it("tools/list expõe as seis tools amp_*", async () => {
    const { tools } = await client.listTools();
    const names = tools.map((t) => t.name).sort();
    expect(names).toEqual([
      "amp_groups",
      "amp_history",
      "amp_inbox",
      "amp_presence",
      "amp_send",
      "amp_status",
    ]);
  });

  it("amp_status reflete a conexão real com o hub", async () => {
    const status = payload(await client.callTool({ name: "amp_status", arguments: {} })) as {
      agent_id: string;
      connected: boolean;
    };
    expect(status.agent_id).toBe(AGENT);
    expect(status.connected).toBe(true);
  });

  it("amp_inbox lê a mensagem que o hub entregou (pendente do hello)", async () => {
    const inbox = payload(
      await client.callTool({ name: "amp_inbox", arguments: { unread_only: true } }),
    ) as { messages: Array<{ from: string; body: string }> };
    expect(inbox.messages.some((m) => m.body === "tem reset de senha?")).toBe(true);
  });

  it("amp_send roteia pelo socket do daemon até o hub", async () => {
    const res = payload(
      await client.callTool({
        name: "amp_send",
        arguments: { to: PEER, body: "oi via MCP", type: "request" },
      }),
    ) as { sent: boolean };
    expect(res.sent).toBe(true);
    await waitFor(
      () => hub.sentMessages().some((m) => m.to === PEER && m.body === "oi via MCP"),
      5000,
      "mensagem chegou ao hub via MCP",
    );
  });

  it("amp_send com destino inválido devolve erro pela tool (isError)", async () => {
    const res = (await client.callTool({
      name: "amp_send",
      arguments: { to: "x", body: "vazio?" }, // 'x' viola o regex de destinatário
    })) as { isError?: boolean; content: Array<{ type: string; text?: string }> };
    expect(res.isError).toBe(true);
  });
});
