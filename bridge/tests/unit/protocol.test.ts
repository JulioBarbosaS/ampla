import { describe, expect, it } from "vitest";
import { parseServerFrame } from "../../src/shared/protocol.js";

// Fixtures identical to what the hub serializes (hub/app/schemas/ws.py)
const WIRE_MESSAGE = {
  id: 1,
  from: "mobile-eduardo",
  to: "backend-julio",
  body: "Existe endpoint de reset?",
  type: "request" as const,
  priority: "normal" as const,
  group: null,
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
  allow_write: false,
  block_hidden_files: true,
  block_sensitive_paths: true,
  confine_to_dir: true,
  denied_paths: [],
  trusted_senders: [],
  auto_paused: false,
  max_auto_tokens_per_day: null,
  max_auto_cost_usd_per_day: null,
  require_approval: false,
};

describe("parseServerFrame", () => {
  it("accepts a complete hello_ack from the hub", () => {
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

  it("accepts all server frame types", () => {
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

  it("returns null for an invalid frame without throwing", () => {
    expect(parseServerFrame("não é json")).toBeNull();
    expect(parseServerFrame(JSON.stringify({ type: "desconhecido" }))).toBeNull();
    expect(parseServerFrame(JSON.stringify({ type: "message" }))).toBeNull();
  });
});
