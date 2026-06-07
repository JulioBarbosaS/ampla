/**
 * Conexão WS do painel (observer): recebe message/presence em tempo real.
 * Único ponto de acesso WS (docs/ARCHITECTURE.md · Regras web).
 */

import { wsUrl } from "../api/client";
import type { Message } from "../api/types";

export interface ObserverHandlers {
  onMessage: (message: Message) => void;
  onPresence: (agentId: string, online: boolean) => void;
  onOnlineList: (slugs: string[]) => void;
  /** Status da conexão do painel (true após hello_ack, false ao cair). */
  onStatus?: (connected: boolean) => void;
}

const RECONNECT_MS = 3000;

/** Conecta como observer; retorna função de cleanup. */
export function connectObserver(token: string, handlers: ObserverHandlers): () => void {
  let ws: WebSocket | null = null;
  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | null = null;

  function open(): void {
    ws = new WebSocket(wsUrl());
    ws.onopen = () => ws?.send(JSON.stringify({ type: "hello", jwt: token }));
    ws.onmessage = (event) => {
      let frame: { type?: string; [k: string]: unknown };
      try {
        frame = JSON.parse(String(event.data));
      } catch {
        return;
      }
      if (frame.type === "hello_ack") {
        handlers.onStatus?.(true);
        handlers.onOnlineList((frame.online as string[]) ?? []);
      } else if (frame.type === "message") {
        handlers.onMessage(frame.message as Message);
      } else if (frame.type === "presence") {
        handlers.onPresence(String(frame.agent_id), frame.status === "online");
      }
    };
    ws.onclose = () => {
      handlers.onStatus?.(false);
      if (!stopped) {
        timer = setTimeout(open, RECONNECT_MS);
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
