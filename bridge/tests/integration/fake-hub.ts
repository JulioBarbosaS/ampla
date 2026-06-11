/**
 * Fake hub for daemon integration tests: a real WebSocket server
 * that speaks the hub protocol (hello → hello_ack, delivered, push).
 */

import { once } from "node:events";
import type { AddressInfo } from "node:net";
import { type WebSocket, WebSocketServer } from "ws";
import type { AgentSettings, WireMessage } from "../../src/shared/protocol.js";

export class FakeHub {
  private wss: WebSocketServer | null = null;
  readonly received: Array<{ type: string; [k: string]: unknown }> = [];
  readonly sockets = new Map<string, WebSocket>();
  settings: AgentSettings = {
    mode: "inbox",
    allowed_senders: null,
    max_auto_per_hour: 10,
    auto_timeout_secs: 120,
    instructions: "",
    allow_write: false,
    block_hidden_files: true,
    block_sensitive_paths: true,
    confine_to_dir: true,
    denied_paths: [],
    trusted_senders: [],
    auto_paused: false,
    max_auto_tokens_per_day: null,
    max_auto_cost_usd_per_day: null,
  };
  pending: WireMessage[] = [];
  validKeys = new Map<string, string>(); // agent_id -> key
  autoResponderEnabled = true; // global kill switch state sent in hello_ack
  private nextId = 1000;

  async start(): Promise<string> {
    this.wss = new WebSocketServer({ port: 0 });
    await once(this.wss, "listening");

    this.wss.on("connection", (ws) => {
      let agentId: string | null = null;
      ws.on("message", (data) => {
        const frame = JSON.parse(data.toString());
        this.received.push(frame);

        if (frame.type === "hello") {
          if (this.validKeys.get(frame.agent_id) !== frame.key) {
            ws.send(
              JSON.stringify({
                type: "error",
                code: "auth_failed",
                detail: "Chave inválida ou revogada.",
              }),
            );
            ws.close(4401, "auth failed");
            return;
          }
          agentId = frame.agent_id;
          this.sockets.set(frame.agent_id, ws);
          ws.send(
            JSON.stringify({
              type: "hello_ack",
              agent_id: frame.agent_id,
              online: [frame.agent_id],
              settings: this.settings,
              pending: this.pending,
              auto_responder_enabled: this.autoResponderEnabled,
            }),
          );
        } else if (frame.type === "message" && agentId) {
          ws.send(JSON.stringify({ type: "delivered", message_id: this.nextId++, to: frame.to }));
        }
      });
      ws.on("close", () => {
        if (agentId) this.sockets.delete(agentId);
      });
    });

    const { port } = this.wss.address() as AddressInfo;
    return `ws://127.0.0.1:${port}`;
  }

  /** Pushes a message to the connected daemon (as the real hub would). */
  pushMessage(to: string, message: WireMessage): void {
    this.sockets.get(to)?.send(JSON.stringify({ type: "message", message }));
  }

  pushSettings(to: string, settings: AgentSettings): void {
    this.settings = settings;
    this.sockets.get(to)?.send(JSON.stringify({ type: "settings_update", settings }));
  }

  /** Flips the global kill switch and notifies the connected daemon. */
  pushKillSwitch(to: string, enabled: boolean): void {
    this.autoResponderEnabled = enabled;
    this.sockets
      .get(to)
      ?.send(JSON.stringify({ type: "kill_switch", auto_responder_enabled: enabled }));
  }

  /** Heartbeat: the hub pings the daemon (which must reply pong). */
  pushPing(to: string): void {
    this.sockets.get(to)?.send(JSON.stringify({ type: "ping" }));
  }

  /** How many `pong` frames the daemon sent to the hub. */
  pongs(): number {
    return this.received.filter((f) => f.type === "pong").length;
  }

  /** `message` frames sent by the daemon to the hub. */
  sentMessages(): Array<{ to: string; body: string }> {
    return this.received
      .filter((f) => f.type === "message")
      .map((f) => ({ to: String(f.to), body: String(f.body) }));
  }

  /** message_ids confirmed by the daemon via the `ack` frame (at-least-once). */
  acks(): number[] {
    return this.received.filter((f) => f.type === "ack").map((f) => Number(f.message_id));
  }

  /** `activity` states (responding…/idle) the daemon signaled, in order. */
  activities(): string[] {
    return this.received.filter((f) => f.type === "activity").map((f) => String(f.state));
  }

  /** auto-respond run records the daemon reported (Epic 03 · 3.1). */
  autorespondReports(): Array<Record<string, unknown>> {
    return this.received
      .filter((f) => f.type === "autorespond_report")
      .map((f) => f.record as Record<string, unknown>);
  }

  async stop(): Promise<void> {
    for (const ws of this.sockets.values()) ws.terminate();
    await new Promise<void>((resolve) => this.wss?.close(() => resolve()));
  }
}

export function wireMessage(
  id: number,
  from: string,
  to: string,
  body: string,
  overrides: Partial<WireMessage> = {},
): WireMessage {
  return {
    id,
    from,
    to,
    body,
    type: "request",
    priority: "normal",
    group: null,
    thread_id: id,
    in_reply_to: null,
    created_at: new Date().toISOString(),
    delivered_at: null,
    expires_at: null,
    ...overrides,
  };
}

export async function waitFor(
  condition: () => boolean,
  timeoutMs = 5000,
  label = "condição",
): Promise<void> {
  const start = Date.now();
  while (!condition()) {
    if (Date.now() - start > timeoutMs) {
      throw new Error(`timeout esperando ${label}`);
    }
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
}
