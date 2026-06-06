/**
 * Golden de espelhamento do protocolo (docs/ARCHITECTURE.md · Protocolo WS):
 * lê hub/tests/golden/ws_frames.json — o MESMO arquivo gerado e validado
 * pelo hub — e prova que este lado fala exatamente a mesma língua.
 *
 * Se este teste quebrar: hub e bridge divergiram. Alinhe protocol.ts com
 * hub/app/schemas/ws.py NO MESMO COMMIT e regenere o golden no hub
 * (AMP_UPDATE_GOLDEN=1 pytest tests/golden).
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import type { ClientFrame } from "../../src/shared/protocol.js";
import { parseServerFrame, serverFrameSchema } from "../../src/shared/protocol.js";

const GOLDEN_PATH = resolve(import.meta.dirname, "../../../hub/tests/golden/ws_frames.json");
const golden: Record<string, Record<string, unknown>> = JSON.parse(
  readFileSync(GOLDEN_PATH, "utf-8"),
);

describe("espelhamento hub ↔ bridge (golden compartilhado)", () => {
  const serverKeys = Object.keys(golden).filter((k) => k.startsWith("server."));
  const clientKeys = Object.keys(golden).filter((k) => k.startsWith("client."));

  it("o golden cobre os dois sentidos", () => {
    expect(serverKeys.length).toBeGreaterThanOrEqual(6);
    expect(clientKeys.length).toBeGreaterThanOrEqual(2);
  });

  it.each(serverKeys)("bridge entende o frame do hub: %s", (key) => {
    const frame = parseServerFrame(JSON.stringify(golden[key]));
    expect(frame, `frame ${key} rejeitado pelo protocol.ts`).not.toBeNull();
    // estrito: nenhum campo do hub pode passar despercebido pelo schema TS
    expect(serverFrameSchema.parse(golden[key])).toEqual(golden[key]);
  });

  it("bridge produz client.hello byte-idêntico ao contrato", () => {
    const hello: ClientFrame = {
      type: "hello",
      agent_id: "backend-julio",
      key: `amp_${"ab".repeat(32)}`,
    };
    expect(JSON.parse(JSON.stringify(hello))).toEqual(golden["client.hello"]);
  });

  it("bridge produz client.message byte-idêntico ao contrato", () => {
    const message: ClientFrame = {
      type: "message",
      to: "backend-julio",
      body: "Existe endpoint de reset de senha?",
    };
    expect(JSON.parse(JSON.stringify(message))).toEqual(golden["client.message"]);
  });
});
