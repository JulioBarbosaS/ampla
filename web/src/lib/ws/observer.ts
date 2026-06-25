/**
 * Panel WS connection (observer): receives message/presence in real time.
 * Single WS entry point (docs/ARCHITECTURE.md · web rules).
 */

import { wsUrl } from "../api/client";
import type { AppNotification, KanbanDelta, Message } from "../api/types";

export interface ObserverHandlers {
  onMessage: (message: Message) => void;
  onPresence: (agentId: string, online: boolean) => void;
  onOnlineList: (slugs: string[]) => void;
  /** Panel connection status (true after hello_ack, false on drop). */
  onStatus?: (connected: boolean) => void;
  /** Delivery confirmation for a message (at-least-once): the recipient
   * acked and the hub re-mirrored — updates the "delivered" mark on the bubble. */
  onDelivered?: (messageId: number) => void;
  /** An agent started/stopped generating an auto-reply ("responding…"). */
  onActivity?: (agentId: string, responding: boolean) => void;
  /** Global kill switch state (from hello_ack and live kill_switch frames). */
  onKillSwitch?: (enabled: boolean) => void;
  /** A new or collapsed inbox notification arrived for this user. */
  onNotification?: (notification: AppNotification) => void;
  /** Read-state synced from another tab/device: ids (or "all") + badge count. */
  onNotificationRead?: (ids: number[] | "all", unreadCount: number) => void;
  /** A live Kanban board change for a board this user can see (Epic 06 · 6.5). */
  onKanbanDelta?: (delta: KanbanDelta) => void;
  /** Fired after the socket recovers from a drop (a hello_ack on a re-opened
   * socket, never the first connect). The consumer should re-fetch to catch up
   * on frames that arrived while the socket was down — they are NOT replayed. */
  onReconnect?: () => void;
}

// Exponential backoff with 50–100% jitter — same shape as the bridge's
// ws-client, capped tighter since a human is watching this tab.
const BACKOFF_BASE_MS = 1_000;
const BACKOFF_MAX_MS = 30_000;

/** Connects as observer; returns a cleanup function. The session rides on the
 * HttpOnly cookie carried with the WS upgrade (same origin) — no token in JS. */
export function connectObserver(handlers: ObserverHandlers): () => void {
  let ws: WebSocket | null = null;
  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let attempts = 0;
  let connectedOnce = false;

  function nextDelay(): number {
    const exp = Math.min(BACKOFF_BASE_MS * 2 ** attempts, BACKOFF_MAX_MS);
    attempts += 1;
    return Math.round(exp / 2 + Math.random() * (exp / 2));
  }

  function open(): void {
    ws = new WebSocket(wsUrl());
    ws.onopen = () => ws?.send(JSON.stringify({ type: "hello" }));
    ws.onmessage = (event) => {
      let frame: { type?: string; [k: string]: unknown };
      try {
        frame = JSON.parse(String(event.data));
      } catch {
        return;
      }
      if (frame.type === "hello_ack") {
        attempts = 0; // a healthy connection resets the backoff
        handlers.onStatus?.(true);
        handlers.onOnlineList((frame.online as string[]) ?? []);
        // absent on older hubs → treat as enabled (normal operation)
        handlers.onKillSwitch?.(frame.auto_responder_enabled !== false);
        // A hello_ack on any socket after the first means we just recovered.
        if (connectedOnce) handlers.onReconnect?.();
        connectedOnce = true;
      } else if (frame.type === "kill_switch") {
        handlers.onKillSwitch?.(frame.auto_responder_enabled === true);
      } else if (frame.type === "notification") {
        handlers.onNotification?.(frame.notification as AppNotification);
      } else if (frame.type === "notification_read") {
        const ids = frame.ids as number[] | "all";
        handlers.onNotificationRead?.(ids, Number(frame.unread_count));
      } else if (frame.type === "message") {
        handlers.onMessage(frame.message as Message);
      } else if (frame.type === "delivered") {
        handlers.onDelivered?.(Number(frame.message_id));
      } else if (frame.type === "presence") {
        handlers.onPresence(String(frame.agent_id), frame.status === "online");
      } else if (frame.type === "agent_activity") {
        handlers.onActivity?.(String(frame.agent_id), frame.state === "responding");
      } else if (frame.type === "kanban_delta") {
        handlers.onKanbanDelta?.(frame as unknown as KanbanDelta);
      }
    };
    ws.onclose = () => {
      handlers.onStatus?.(false);
      if (!stopped) {
        timer = setTimeout(open, nextDelay());
      }
    };
  }

  open();
  return () => {
    stopped = true;
    if (timer) clearTimeout(timer);
    ws?.close();
  };
}
