/**
 * MCP shell smoke test: connects a REAL MCP client (MCP protocol, via an
 * in-memory transport) to the `buildServer()` server and exercises the
 * amp_* tools against a live daemon (unix socket) wired to a fake hub.
 *
 * Closes the gap from PLAN-onboarding-smoke: until now only the daemon's
 * local-api had a test; the MCP layer (tools/list, tools/call → socket → hub) had
 * never been exercised. Does not use the real `claude` — validates the shell, not the account.
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

/** Reads the JSON the tool returns as text (asText: JSON.stringify). */
function payload(result: { content: Array<{ type: string; text?: string }> }): unknown {
  const text = result.content.find((c) => c.type === "text")?.text ?? "{}";
  return JSON.parse(text);
}

beforeAll(async () => {
  dir = mkdtempSync(join(tmpdir(), "amp-mcp-"));
  // AMP_HOME must be set BEFORE importing the MCP module: the
  // DaemonClient singleton resolves socketPath() at load time.
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

  // Real MCP server + real MCP client, wired by an in-memory transport.
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

describe("MCP smoke: real client ↔ real server ↔ daemon", () => {
  it("tools/list exposes the amp_* tools", async () => {
    const { tools } = await client.listTools();
    const names = tools.map((t) => t.name).sort();
    expect(names).toEqual([
      "amp_delegate",
      "amp_groups",
      "amp_history",
      "amp_inbox",
      "amp_kanban_boards",
      "amp_kanban_cards",
      "amp_kanban_comment",
      "amp_kanban_create_card",
      "amp_kanban_move_card",
      "amp_presence",
      "amp_send",
      "amp_status",
    ]);
  });

  it("amp_kanban_create_card routes a kanban_action frame through the daemon to the hub", async () => {
    const res = payload(
      await client.callTool({
        name: "amp_kanban_create_card",
        arguments: { board: 1, title: "Card via MCP", priority: "high" },
      }),
    ) as { queued: boolean };
    expect(res.queued).toBe(true);
    await waitFor(
      () =>
        hub
          .sentKanbanActions()
          .some((a) => a.op === "create_card" && a.payload.title === "Card via MCP"),
      5000,
      "kanban_action chegou ao hub via MCP",
    );
  });

  it("amp_status reflects the real connection to the hub", async () => {
    const status = payload(await client.callTool({ name: "amp_status", arguments: {} })) as {
      agent_id: string;
      connected: boolean;
    };
    expect(status.agent_id).toBe(AGENT);
    expect(status.connected).toBe(true);
  });

  it("amp_inbox reads the message the hub delivered (hello pending)", async () => {
    const inbox = payload(
      await client.callTool({ name: "amp_inbox", arguments: { unread_only: true } }),
    ) as { messages: Array<{ from: string; body: string }> };
    expect(inbox.messages.some((m) => m.body === "tem reset de senha?")).toBe(true);
  });

  it("amp_send routes through the daemon socket to the hub", async () => {
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

  it("amp_send with an invalid destination returns an error via the tool (isError)", async () => {
    const res = (await client.callTool({
      name: "amp_send",
      arguments: { to: "x", body: "vazio?" }, // 'x' violates the recipient regex
    })) as { isError?: boolean; content: Array<{ type: string; text?: string }> };
    expect(res.isError).toBe(true);
  });

  it("amp_delegate routes a delegate frame through the daemon socket to the hub", async () => {
    const res = payload(
      await client.callTool({
        name: "amp_delegate",
        arguments: { to: PEER, task: "Revisar o login", context: "ver auth.py" },
      }),
    ) as { delegated: boolean; to: string };
    expect(res.delegated).toBe(true);
    await waitFor(
      () => hub.sentDelegations().some((d) => d.to === PEER && d.task === "Revisar o login"),
      5000,
      "delegação chegou ao hub via MCP",
    );
  });
});
