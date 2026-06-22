/**
 * Daemon WebSocket client — sole owner of the connection to the hub.
 * Reconnection with exponential backoff + jitter; presence kept locally.
 */

import { EventEmitter } from "node:events";
import WebSocket from "ws";
import {
  type AgentSettings,
  type AutorespondRecord,
  type ClientFrame,
  type GroupInfo,
  type HelloAckFrame,
  type MessageType,
  type Priority,
  parseServerFrame,
  type WireMessage,
} from "../shared/protocol.js";

export interface HubClientEvents {
  ack: [HelloAckFrame];
  message: [WireMessage];
  delivered: [{ message_id: number; to: string }];
  presence: [{ agent_id: string; status: "online" | "offline" }];
  settings: [AgentSettings];
  broadcastResult: [{ group: string; sent: string[]; skipped: string[]; offline: string[] }];
  hubError: [{ code: string; detail: string }];
  killSwitch: [{ autoResponderEnabled: boolean }];
  down: [{ willRetry: boolean; delayMs: number }];
}

const BACKOFF_BASE_MS = 1_000;
const BACKOFF_MAX_MS = 60_000;
/** Hub codes that indicate a permanent error — reconnecting won't help. */
const FATAL_CLOSE_CODES = new Set([4401]);

export class HubClient extends EventEmitter<HubClientEvents> {
  private ws: WebSocket | null = null;
  private attempts = 0;
  private stopped = false;
  private reconnectTimer: NodeJS.Timeout | null = null;
  private readonly online = new Set<string>();
  settings: AgentSettings | null = null;
  groups: GroupInfo[] = [];
  /** Global kill switch (Epic 03 · 3.2). True = auto-respond allowed. Learned
   * from hello_ack and updated live by `kill_switch` frames. */
  autoResponderEnabled = true;

  constructor(
    private readonly hubUrl: string,
    private readonly agentId: string,
    private readonly agentKey: string,
  ) {
    super();
  }

  get connected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  onlineAgents(): string[] {
    return [...this.online].sort();
  }

  start(): void {
    this.stopped = false;
    this.connect();
  }

  stop(): void {
    this.stopped = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close(1000, "shutdown");
    this.ws = null;
  }

  send(
    to: string,
    body: string,
    opts: { msgType?: MessageType; priority?: Priority; inReplyTo?: number } = {},
  ): boolean {
    const ws = this.ws;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    const frame: ClientFrame = {
      type: "message",
      to,
      body,
      ...(opts.msgType ? { msg_type: opts.msgType } : {}),
      ...(opts.priority ? { priority: opts.priority } : {}),
      ...(opts.inReplyTo !== undefined ? { in_reply_to: opts.inReplyTo } : {}),
    };
    ws.send(JSON.stringify(frame));
    return true;
  }

  /** Signals to the hub (and thus the panel) that this agent started or finished
   * generating an auto-reply — drives the "responding…" indicator. Best-effort:
   * a dropped signal only affects a transient UI hint. */
  sendActivity(state: "responding" | "idle"): boolean {
    const ws = this.ws;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    const frame: ClientFrame = { type: "activity", state };
    ws.send(JSON.stringify(frame));
    return true;
  }

  /** Reports an auto-respond run to the hub for the auditable transcript
   * (Epic 03 · 3.1). Best-effort: a dropped report only loses one audit row. */
  sendAutorespondReport(record: AutorespondRecord): boolean {
    const ws = this.ws;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    const frame: ClientFrame = { type: "autorespond_report", record };
    ws.send(JSON.stringify(frame));
    return true;
  }

  /** Requests the owner's approval for a drafted auto-reply instead of sending
   * it (Epic 03 · 3.3). The hub persists it under the authenticated agent and
   * notifies the owner; on approval the hub sends server-side. */
  sendApprovalRequest(triggerMessageId: number | null, to: string, draftBody: string): boolean {
    const ws = this.ws;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    const frame: ClientFrame = {
      type: "approval_request",
      trigger_message_id: triggerMessageId,
      to,
      draft_body: draftBody,
    };
    ws.send(JSON.stringify(frame));
    return true;
  }

  /** Delegates a task to another agent (Epic 04 · 4.4). The hub creates a
   * delegations row + a task message to the delegate, attributed to this
   * authenticated agent. Only reachable from an interactive session (the
   * auto-responder runs with --strict-mcp-config and has no ampla MCP). */
  sendDelegate(to: string, task: string, context: string): boolean {
    const ws = this.ws;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    const frame: ClientFrame = { type: "delegate", to, task, context };
    ws.send(JSON.stringify(frame));
    return true;
  }

  /** Acts on a Kanban board (Epic 06 · 6.4). No actor field — the hub attributes
   * it to this authenticated agent and re-checks the per-agent capability (§6.3).
   * Only reachable from an interactive session (the auto-responder runs with
   * --strict-mcp-config and has no ampla MCP). Fire-and-forget like delegate; a
   * rejection comes back as an `error` frame and the change streams as a delta. */
  sendKanbanAction(
    boardId: number,
    op: "create_card" | "move_card" | "comment",
    payload: Record<string, unknown>,
  ): boolean {
    const ws = this.ws;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    const frame: ClientFrame = { type: "kanban_action", board_id: boardId, op, payload };
    ws.send(JSON.stringify(frame));
    return true;
  }

  /** Reads the board over the hub's REST API using THIS agent's key (Epic 06 ·
   * 6.4). Writes go over the WS; reads need real data, so the daemon proxies the
   * agent-key-authenticated GETs. The hub applies the same per-agent capability. */
  async kanbanGet(path: string): Promise<unknown> {
    const base = this.hubUrl.replace(/^ws/, "http").replace(/\/ws$/, "");
    const res = await fetch(`${base}${path}`, {
      headers: { Authorization: `Bearer ${this.agentKey}`, "X-Amp-Agent": this.agentId },
    });
    if (!res.ok) {
      const detail = await res.text().catch(() => "");
      throw new Error(`hub respondeu ${res.status}${detail ? `: ${detail}` : ""}`);
    }
    return res.json();
  }

  /** Confirms receipt of a message (at-least-once): the hub only marks it
   * `delivered` and notifies the sender after this ack. Always ack — even a
   * deduplicated message — otherwise the hub resends it on every reconnect. */
  ackMessage(messageId: number): boolean {
    const ws = this.ws;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    const frame: ClientFrame = { type: "ack", message_id: messageId };
    ws.send(JSON.stringify(frame));
    return true;
  }

  private connect(): void {
    const ws = new WebSocket(this.hubUrl);
    this.ws = ws;

    ws.on("open", () => {
      const hello: ClientFrame = {
        type: "hello",
        agent_id: this.agentId,
        key: this.agentKey,
      };
      ws.send(JSON.stringify(hello));
    });

    ws.on("message", (data) => {
      const frame = parseServerFrame(data.toString());
      if (!frame) return; // unknown frame is ignored, never crashes the daemon

      switch (frame.type) {
        case "hello_ack":
          this.attempts = 0;
          this.online.clear();
          for (const slug of frame.online) this.online.add(slug);
          if (frame.settings) this.settings = frame.settings;
          this.groups = frame.groups;
          this.autoResponderEnabled = frame.auto_responder_enabled;
          this.emit("ack", frame);
          for (const pending of frame.pending) this.emit("message", pending);
          break;
        case "message":
          this.emit("message", frame.message);
          break;
        case "delivered":
          this.emit("delivered", { message_id: frame.message_id, to: frame.to });
          break;
        case "presence":
          if (frame.status === "online") this.online.add(frame.agent_id);
          else this.online.delete(frame.agent_id);
          this.emit("presence", frame);
          break;
        case "settings_update":
          this.settings = frame.settings;
          this.emit("settings", frame.settings);
          break;
        case "broadcast_result":
          this.emit("broadcastResult", {
            group: frame.group,
            sent: frame.sent,
            skipped: frame.skipped,
            offline: frame.offline,
          });
          break;
        case "kill_switch":
          this.autoResponderEnabled = frame.auto_responder_enabled;
          this.emit("killSwitch", { autoResponderEnabled: frame.auto_responder_enabled });
          break;
        case "ping":
          // heartbeat: respond immediately so we are not considered a zombie
          ws.send(JSON.stringify({ type: "pong" } satisfies ClientFrame));
          break;
        case "error":
          this.emit("hubError", { code: frame.code, detail: frame.detail });
          break;
      }
    });

    ws.on("close", (code) => {
      this.online.clear();
      if (this.ws === ws) this.ws = null;
      if (this.stopped || FATAL_CLOSE_CODES.has(code)) {
        this.emit("down", { willRetry: false, delayMs: 0 });
        return;
      }
      const delayMs = this.nextDelay();
      this.emit("down", { willRetry: true, delayMs });
      this.reconnectTimer = setTimeout(() => this.connect(), delayMs);
    });

    ws.on("error", () => {
      // 'close' is emitted next; the backoff happens there
    });
  }

  private nextDelay(): number {
    const exp = Math.min(BACKOFF_BASE_MS * 2 ** this.attempts, BACKOFF_MAX_MS);
    this.attempts += 1;
    return Math.round(exp / 2 + Math.random() * (exp / 2)); // jitter 50–100%
  }
}
