/**
 * Hub fake para testes de integração do daemon: WebSocket server real
 * que fala o protocolo do hub (hello → hello_ack, delivered, push).
 */

import { once } from "node:events";
import { type AddressInfo } from "node:net";
import { WebSocket, WebSocketServer } from "ws";
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
  };
  pending: WireMessage[] = [];
  validKeys = new Map<string, string>(); // agent_id -> key
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
              })
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
            })
          );
        } else if (frame.type === "message" && agentId) {
          ws.send(
            JSON.stringify({ type: "delivered", message_id: this.nextId++, to: frame.to })
          );
        }
      });
      ws.on("close", () => {
        if (agentId) this.sockets.delete(agentId);
      });
    });

    const { port } = this.wss.address() as AddressInfo;
    return `ws://127.0.0.1:${port}`;
  }

  /** Empurra uma mensagem para o daemon conectado (como o hub real faria). */
  pushMessage(to: string, message: WireMessage): void {
    this.sockets.get(to)?.send(JSON.stringify({ type: "message", message }));
  }

  pushSettings(to: string, settings: AgentSettings): void {
    this.settings = settings;
    this.sockets.get(to)?.send(JSON.stringify({ type: "settings_update", settings }));
  }

  /** Frames `message` enviados pelo daemon ao hub. */
  sentMessages(): Array<{ to: string; body: string }> {
    return this.received
      .filter((f) => f.type === "message")
      .map((f) => ({ to: String(f.to), body: String(f.body) }));
  }

  async stop(): Promise<void> {
    for (const ws of this.sockets.values()) ws.terminate();
    await new Promise<void>((resolve) => this.wss?.close(() => resolve()));
  }
}

export function wireMessage(id: number, from: string, to: string, body: string): WireMessage {
  return {
    id,
    from,
    to,
    body,
    created_at: new Date().toISOString(),
    delivered_at: null,
  };
}

export async function waitFor(
  condition: () => boolean,
  timeoutMs = 5000,
  label = "condição"
): Promise<void> {
  const start = Date.now();
  while (!condition()) {
    if (Date.now() - start > timeoutMs) {
      throw new Error(`timeout esperando ${label}`);
    }
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
}
