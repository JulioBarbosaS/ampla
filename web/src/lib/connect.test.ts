import { describe, expect, it } from "vitest";
import { connectToken } from "./connect";

/** Decodifica o token base64url → JSON (equivalente ao Buffer base64url do CLI). */
function decode(token: string): unknown {
  const b64 = token.replace(/-/g, "+").replace(/_/g, "/");
  const padded = b64 + "=".repeat((4 - (b64.length % 4)) % 4);
  return JSON.parse(decodeURIComponent(escape(atob(padded))));
}

describe("connectToken", () => {
  it("faz round-trip com o decode do CLI (base64url de {hub_url,agent_id,key})", () => {
    const token = connectToken("ws://localhost:8000/ws", "backend-julio", "amp_abc123");
    expect(decode(token)).toEqual({
      hub_url: "ws://localhost:8000/ws",
      agent_id: "backend-julio",
      key: "amp_abc123",
    });
  });

  it("não usa caracteres não-url-safe (+ / =)", () => {
    const token = connectToken(
      "wss://hub.exemplo.com/ws",
      "infra-maria-do-time",
      `amp_${"z".repeat(64)}`,
    );
    expect(token).not.toMatch(/[+/=]/);
  });
});
