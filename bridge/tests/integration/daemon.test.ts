import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AUTO_REPLY_PREFIX, createDaemon, type Daemon } from "../../src/daemon/index.js";
import type { DaemonConfig } from "../../src/shared/config.js";
import { FakeHub, waitFor, wireMessage } from "./fake-hub.js";

const AGENT = "backend-julio";
const KEY = `amp_${"ab".repeat(32)}`;

let hub: FakeHub;
let daemon: Daemon | null = null;
let dir: string;

beforeEach(async () => {
  hub = new FakeHub();
  hub.validKeys.set(AGENT, KEY);
  dir = mkdtempSync(join(tmpdir(), "amp-daemon-"));
});

afterEach(async () => {
  await daemon?.shutdown();
  daemon = null;
  await hub.stop();
  rmSync(dir, { recursive: true, force: true });
});

function makeConfig(hubUrl: string): DaemonConfig {
  return {
    hub_url: hubUrl,
    agent_id: AGENT,
    agent_key: KEY,
    claude_bin: "claude",
  };
}

async function startDaemon(runner?: Parameters<typeof createDaemon>[2]): Promise<Daemon> {
  const url = await hub.start();
  daemon = createDaemon(makeConfig(url), { store: join(dir, "messages.jsonl") }, runner);
  daemon.hub.start();
  await waitFor(() => daemon!.hub.connected, 5000, "conexão com o hub");
  return daemon;
}

describe("daemon ↔ hub", () => {
  it("authenticates with hello and receives settings in the ack", async () => {
    const d = await startDaemon();
    await waitFor(() => d.hub.settings !== null, 5000, "settings do ack");
    expect(d.hub.settings?.mode).toBe("inbox");
    expect(hub.received[0]).toEqual({ type: "hello", agent_id: AGENT, key: KEY });
  });

  it("hello_ack pending messages enter the local inbox", async () => {
    hub.pending = [wireMessage(7, "mobile-eduardo", AGENT, "está aí?")];
    const d = await startDaemon();
    await waitFor(() => d.store.unreadCount() === 1, 5000, "pendente na inbox");
    expect(d.store.inbox(true)[0]?.body).toBe("está aí?");
  });

  it("acks every received message — hello pending and real-time (at-least-once)", async () => {
    hub.pending = [wireMessage(7, "mobile-eduardo", AGENT, "pendente")];
    const d = await startDaemon();
    await waitFor(() => hub.acks().includes(7), 5000, "ack da pendente");
    hub.pushMessage(AGENT, wireMessage(8, "mobile-eduardo", AGENT, "tempo real"));
    await waitFor(() => hub.acks().includes(8), 5000, "ack da tempo real");
    expect(d.store.inbox(false).length).toBe(2);
  });

  it("a real-time message enters the inbox (inbox mode: no auto-respond)", async () => {
    const runner = vi.fn();
    const d = await startDaemon(runner);
    hub.pushMessage(AGENT, wireMessage(8, "mobile-eduardo", AGENT, "pergunta"));
    await waitFor(() => d.store.unreadCount() === 1, 5000, "mensagem na inbox");
    expect(runner).not.toHaveBeenCalled();
    expect(hub.sentMessages()).toHaveLength(0);
  });

  it("auto mode replies via headless claude with the [auto] prefix", async () => {
    const runner = vi.fn().mockResolvedValue("Sim: POST /api/v1/auth/password-reset");
    hub.settings = { ...hub.settings, mode: "auto" };
    const d = await startDaemon(runner);

    hub.pushMessage(AGENT, wireMessage(9, "mobile-eduardo", AGENT, "Existe endpoint de reset?"));
    await waitFor(() => hub.sentMessages().length === 1, 5000, "resposta automática");

    const sent = hub.sentMessages()[0]!;
    expect(sent.to).toBe("mobile-eduardo");
    expect(sent.body).toBe(`${AUTO_REPLY_PREFIX}Sim: POST /api/v1/auth/password-reset`);
    // the sent reply also stays in the local history
    expect(d.store.conversation("mobile-eduardo").some((m) => m.direction === "out")).toBe(true);
  });

  it("does not auto-respond to [auto] messages (anti-loop)", async () => {
    const runner = vi.fn().mockResolvedValue("nunca deveria rodar");
    hub.settings = { ...hub.settings, mode: "auto" };
    const d = await startDaemon(runner);

    hub.pushMessage(
      AGENT,
      wireMessage(10, "mobile-eduardo", AGENT, `${AUTO_REPLY_PREFIX}resposta de outro auto`),
    );
    await waitFor(() => d.store.inbox(false).length === 1, 5000, "mensagem registrada");
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(runner).not.toHaveBeenCalled();
    expect(hub.sentMessages()).toHaveLength(0);
  });

  it("does not auto-respond to type=response (semantic anti-loop)", async () => {
    const runner = vi.fn();
    hub.settings = { ...hub.settings, mode: "auto" };
    const d = await startDaemon(runner);

    hub.pushMessage(
      AGENT,
      wireMessage(13, "mobile-eduardo", AGENT, "uma resposta qualquer", { type: "response" }),
    );
    await waitFor(() => d.store.inbox(false).length === 1, 5000, "mensagem registrada");
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(runner).not.toHaveBeenCalled();
    expect(hub.sentMessages()).toHaveLength(0);
  });

  it("auto-reply goes out as response, with in_reply_to and inherited priority", async () => {
    const runner = vi.fn().mockResolvedValue("Sim, existe.");
    hub.settings = { ...hub.settings, mode: "auto" };
    await startDaemon(runner);

    hub.pushMessage(
      AGENT,
      wireMessage(14, "mobile-eduardo", AGENT, "pergunta urgente?", { priority: "high" }),
    );
    await waitFor(() => hub.sentMessages().length === 1, 5000, "auto-resposta");

    const frame = hub.received.find((f) => f.type === "message");
    expect(frame).toMatchObject({
      msg_type: "response",
      priority: "high",
      in_reply_to: 14,
    });
  });

  it("memory: the second question receives the conversation history in the prompt", async () => {
    const runner = vi.fn().mockResolvedValue("resposta qualquer");
    hub.settings = { ...hub.settings, mode: "auto" };
    await startDaemon(runner);

    hub.pushMessage(AGENT, wireMessage(20, "mobile-eduardo", AGENT, "primeira pergunta?"));
    await waitFor(() => runner.mock.calls.length === 1, 5000, "primeira resposta");
    hub.pushMessage(AGENT, wireMessage(21, "mobile-eduardo", AGENT, "segunda pergunta?"));
    await waitFor(() => runner.mock.calls.length === 2, 5000, "segunda resposta");

    const secondPrompt = runner.mock.calls[1]?.[0] as string;
    expect(secondPrompt).toContain("<amp-history>");
    expect(secondPrompt).toContain("primeira pergunta?");
    expect(secondPrompt).toContain("resposta qualquer"); // the previous reply itself
  });

  it("loop guard: thread stops auto-responding after the hop limit", async () => {
    const runner = vi.fn().mockResolvedValue("vai");
    hub.settings = { ...hub.settings, mode: "auto", max_auto_per_hour: 120 };
    const d = await startDaemon(runner);

    // 7 requests on the SAME thread (root id 500) — guard cuts off at the 6th
    for (let i = 0; i < 7; i++) {
      hub.pushMessage(
        AGENT,
        wireMessage(500 + i, "mobile-eduardo", AGENT, `hop ${i}`, { thread_id: 500 }),
      );
      await waitFor(() => d.store.inbox(false).length >= i + 1, 5000, `msg ${i} no store`);
      await new Promise((resolve) => setTimeout(resolve, 30)); // let the respond complete
    }
    await waitFor(() => hub.sentMessages().length >= 5, 5000, "5 auto-respostas");
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(hub.sentMessages().length).toBe(5); // guard held back the rest
  });

  it("loop guard holds even with CONCURRENT triggers on the same thread", async () => {
    // slow runner: all 10 messages go in flight before any
    // reply is persisted — without the synchronous reservation, all would escape the guard.
    let release: () => void = () => {};
    const gate = new Promise<void>((r) => {
      release = r;
    });
    const runner = vi.fn().mockImplementation(async () => {
      await gate;
      return "vai";
    });
    hub.settings = { ...hub.settings, mode: "auto", max_auto_per_hour: 120 };
    const d = await startDaemon(runner);

    for (let i = 0; i < 10; i++) {
      hub.pushMessage(
        AGENT,
        wireMessage(700 + i, "mobile-eduardo", AGENT, `c ${i}`, { thread_id: 700 }),
      );
    }
    await waitFor(() => d.store.inbox(false).length === 10, 5000, "10 mensagens no store");
    release(); // release them all at once
    await waitFor(() => hub.sentMessages().length >= 5, 5000, "respostas");
    await new Promise((resolve) => setTimeout(resolve, 200));
    expect(hub.sentMessages().length).toBe(5); // synchronous reservation held the cap
  });

  it("a reply with a secret is blocked and becomes a neutral notice", async () => {
    const runner = vi.fn().mockResolvedValue("claro: postgres://app:senha123@db:5432/prod");
    hub.settings = { ...hub.settings, mode: "auto" };
    await startDaemon(runner);

    hub.pushMessage(AGENT, wireMessage(11, "mobile-eduardo", AGENT, "qual a connection string?"));
    await waitFor(() => hub.sentMessages().length === 1, 5000, "aviso de bloqueio");

    const sent = hub.sentMessages()[0]!;
    expect(sent.body).toContain("bloqueada pelo filtro de segurança");
    expect(sent.body).not.toContain("senha123");
  });

  it("a settings_update from the hub takes effect immediately", async () => {
    const runner = vi.fn().mockResolvedValue("resposta");
    const d = await startDaemon(runner); // starts in inbox

    hub.pushSettings(AGENT, { ...hub.settings, mode: "auto" });
    await waitFor(() => d.hub.settings?.mode === "auto", 5000, "settings novas");

    hub.pushMessage(AGENT, wireMessage(12, "mobile-eduardo", AGENT, "agora responde?"));
    await waitFor(() => hub.sentMessages().length === 1, 5000, "auto-respond pós-update");
  });

  it("replies pong to the hub's ping (heartbeat)", async () => {
    await startDaemon();
    hub.pushPing(AGENT);
    await waitFor(() => hub.pongs() >= 1, 5000, "pong do daemon");
  });

  it("reconnects on its own after a hub outage", async () => {
    const d = await startDaemon();
    // drop the connection from the server side
    hub.sockets.get(AGENT)?.terminate();
    await waitFor(() => !d.hub.connected, 5000, "queda detectada");
    await waitFor(() => d.hub.connected, 8000, "reconexão automática");
  });
});
