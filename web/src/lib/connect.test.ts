import { describe, expect, it } from "vitest";
import { connectToken } from "./connect";

/** Decodes the base64url token → JSON (equivalent to the CLI's base64url Buffer). */
function decode(token: string): unknown {
  const b64 = token.replace(/-/g, "+").replace(/_/g, "/");
  const padded = b64 + "=".repeat((4 - (b64.length % 4)) % 4);
  return JSON.parse(decodeURIComponent(escape(atob(padded))));
}

describe("connectToken", () => {
  it("round-trips with the CLI decode (base64url of {hub_url,agent_id,key})", () => {
    const token = connectToken("ws://localhost:8000/ws", "backend-julio", "amp_abc123");
    expect(decode(token)).toEqual({
      hub_url: "ws://localhost:8000/ws",
      agent_id: "backend-julio",
      key: "amp_abc123",
    });
  });

  it("does not use non-url-safe characters (+ / =)", () => {
    const token = connectToken(
      "wss://hub.exemplo.com/ws",
      "infra-maria-do-time",
      `amp_${"z".repeat(64)}`,
    );
    expect(token).not.toMatch(/[+/=]/);
  });
});
