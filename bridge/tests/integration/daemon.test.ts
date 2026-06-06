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
  it("autentica com hello e recebe settings no ack", async () => {
    const d = await startDaemon();
    await waitFor(() => d.hub.settings !== null, 5000, "settings do ack");
    expect(d.hub.settings?.mode).toBe("inbox");
    expect(hub.received[0]).toEqual({ type: "hello", agent_id: AGENT, key: KEY });
  });

  it("pendentes do hello_ack entram na inbox local", async () => {
    hub.pending = [wireMessage(7, "mobile-eduardo", AGENT, "está aí?")];
    const d = await startDaemon();
    await waitFor(() => d.store.unreadCount() === 1, 5000, "pendente na inbox");
    expect(d.store.inbox(true)[0]?.body).toBe("está aí?");
  });

  it("mensagem em tempo real entra na inbox (modo inbox: sem auto-respond)", async () => {
    const runner = vi.fn();
    const d = await startDaemon(runner);
    hub.pushMessage(AGENT, wireMessage(8, "mobile-eduardo", AGENT, "pergunta"));
    await waitFor(() => d.store.unreadCount() === 1, 5000, "mensagem na inbox");
    expect(runner).not.toHaveBeenCalled();
    expect(hub.sentMessages()).toHaveLength(0);
  });

  it("modo auto responde via claude headless com prefixo [auto]", async () => {
    const runner = vi.fn().mockResolvedValue("Sim: POST /api/v1/auth/password-reset");
    hub.settings = { ...hub.settings, mode: "auto" };
    const d = await startDaemon(runner);

    hub.pushMessage(AGENT, wireMessage(9, "mobile-eduardo", AGENT, "Existe endpoint de reset?"));
    await waitFor(() => hub.sentMessages().length === 1, 5000, "resposta automática");

    const sent = hub.sentMessages()[0]!;
    expect(sent.to).toBe("mobile-eduardo");
    expect(sent.body).toBe(`${AUTO_REPLY_PREFIX}Sim: POST /api/v1/auth/password-reset`);
    // resposta enviada também fica no histórico local
    expect(d.store.conversation("mobile-eduardo").some((m) => m.direction === "out")).toBe(true);
  });

  it("não auto-responde mensagens [auto] (anti-loop)", async () => {
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

  it("não auto-responde type=response (anti-loop semântico)", async () => {
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

  it("auto-resposta sai como response, com in_reply_to e prioridade herdada", async () => {
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

  it("resposta com segredo é bloqueada e vira aviso neutro", async () => {
    const runner = vi.fn().mockResolvedValue("claro: postgres://app:senha123@db:5432/prod");
    hub.settings = { ...hub.settings, mode: "auto" };
    await startDaemon(runner);

    hub.pushMessage(AGENT, wireMessage(11, "mobile-eduardo", AGENT, "qual a connection string?"));
    await waitFor(() => hub.sentMessages().length === 1, 5000, "aviso de bloqueio");

    const sent = hub.sentMessages()[0]!;
    expect(sent.body).toContain("bloqueada pelo filtro de segurança");
    expect(sent.body).not.toContain("senha123");
  });

  it("settings_update do hub passa a valer imediatamente", async () => {
    const runner = vi.fn().mockResolvedValue("resposta");
    const d = await startDaemon(runner); // começa em inbox

    hub.pushSettings(AGENT, { ...hub.settings, mode: "auto" });
    await waitFor(() => d.hub.settings?.mode === "auto", 5000, "settings novas");

    hub.pushMessage(AGENT, wireMessage(12, "mobile-eduardo", AGENT, "agora responde?"));
    await waitFor(() => hub.sentMessages().length === 1, 5000, "auto-respond pós-update");
  });

  it("reconecta sozinho depois de queda do hub", async () => {
    const d = await startDaemon();
    // derruba a conexão pelo lado do servidor
    hub.sockets.get(AGENT)?.terminate();
    await waitFor(() => !d.hub.connected, 5000, "queda detectada");
    await waitFor(() => d.hub.connected, 8000, "reconexão automática");
  });
});
