import { describe, expect, it } from "vitest";
import { parseServerFrame } from "../../src/shared/protocol.js";

// Fixtures idênticas ao que o hub serializa (hub/app/schemas/ws.py)
const WIRE_MESSAGE = {
  id: 1,
  from: "mobile-eduardo",
  to: "backend-julio",
  body: "Existe endpoint de reset?",
  type: "request" as const,
  priority: "normal" as const,
  thread_id: null,
  in_reply_to: null,
  created_at: "2026-06-06T12:00:00Z",
  delivered_at: null,
  expires_at: null,
};

const SETTINGS = {
  mode: "inbox",
  allowed_senders: null,
  max_auto_per_hour: 10,
  auto_timeout_secs: 120,
  instructions: "",
};

describe("parseServerFrame", () => {
  it("aceita hello_ack completo do hub", () => {
    const frame = parseServerFrame(
      JSON.stringify({
        type: "hello_ack",
        agent_id: "backend-julio",
        online: ["backend-julio"],
        settings: SETTINGS,
        pending: [WIRE_MESSAGE],
      }),
    );
    expect(frame?.type).toBe("hello_ack");
    if (frame?.type === "hello_ack") {
      expect(frame.pending[0]?.from).toBe("mobile-eduardo");
      expect(frame.settings?.mode).toBe("inbox");
    }
  });

  it("aceita todos os tipos de frame do servidor", () => {
    const frames = [
      { type: "message", message: WIRE_MESSAGE },
      { type: "delivered", message_id: 1, to: "backend-julio" },
      { type: "presence", agent_id: "infra-maria", status: "offline" },
      { type: "settings_update", settings: { ...SETTINGS, mode: "auto" } },
      { type: "error", code: "rate_limited", detail: "Limite excedido." },
    ];
    for (const raw of frames) {
      expect(parseServerFrame(JSON.stringify(raw))?.type).toBe(raw.type);
    }
  });

  it("retorna null para frame inválido sem lançar", () => {
    expect(parseServerFrame("não é json")).toBeNull();
    expect(parseServerFrame(JSON.stringify({ type: "desconhecido" }))).toBeNull();
    expect(parseServerFrame(JSON.stringify({ type: "message" }))).toBeNull();
  });
});
