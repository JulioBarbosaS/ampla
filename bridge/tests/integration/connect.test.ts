/**
 * `amp connect <token>`: decode/validação do token, merge não-destrutivo
 * dos hooks e a integração que escreve o config (0600) + instala os hooks.
 * MCP é pulado (--no-mcp) para não depender do `claude` real.
 */

import { mkdtempSync, readFileSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { decodeToken, mergeHookSettings, run } from "../../src/cli/connect.js";

const VALID = {
  hub_url: "ws://localhost:8000/ws",
  agent_id: "backend-julio",
  key: `amp_${"ab".repeat(32)}`,
};
const encode = (o: unknown) => Buffer.from(JSON.stringify(o)).toString("base64url");

describe("decodeToken", () => {
  it("decodifica e valida um token bom", () => {
    expect(decodeToken(encode(VALID))).toEqual(VALID);
  });

  it("rejeita base64 que não é JSON", () => {
    expect(() => decodeToken(Buffer.from("xpto").toString("base64url"))).toThrow();
  });

  it("rejeita campos inválidos (chave sem amp_)", () => {
    expect(() => decodeToken(encode({ ...VALID, key: "sem-prefixo" }))).toThrow();
  });

  it("rejeita agent_id fora do padrão de slug", () => {
    expect(() => decodeToken(encode({ ...VALID, agent_id: "Tem Maiúscula" }))).toThrow();
  });
});

describe("mergeHookSettings", () => {
  const entries = [
    { event: "SessionStart" as const, command: "/x/amp-session-start.sh" },
    { event: "UserPromptSubmit" as const, command: "/x/amp-inbox.sh" },
  ];

  it("adiciona os dois hooks", () => {
    const merged = mergeHookSettings({}, entries);
    expect(merged.hooks?.SessionStart).toHaveLength(1);
    expect(merged.hooks?.UserPromptSubmit?.[0]?.hooks?.[0]?.command).toBe("/x/amp-inbox.sh");
  });

  it("é idempotente (não duplica)", () => {
    const once = mergeHookSettings({}, entries);
    const twice = mergeHookSettings(once, entries);
    expect(twice.hooks?.SessionStart).toHaveLength(1);
  });

  it("preserva hooks e chaves já existentes", () => {
    const existing = {
      model: "opus",
      hooks: { SessionStart: [{ hooks: [{ command: "/outro.sh" }] }] },
    };
    const merged = mergeHookSettings(existing, entries) as typeof existing & { model: string };
    expect(merged.model).toBe("opus");
    expect(merged.hooks?.SessionStart).toHaveLength(2); // o do usuário + o nosso
  });
});

describe("run (integração: escreve config + hooks)", () => {
  let fakeHome: string;
  let project: string;
  let prevHome: string | undefined;

  beforeEach(() => {
    prevHome = process.env.HOME;
    fakeHome = mkdtempSync(join(tmpdir(), "amp-connect-home-"));
    project = mkdtempSync(join(tmpdir(), "amp-connect-proj-"));
    process.env.HOME = fakeHome;
  });

  afterEach(() => {
    process.env.HOME = prevHome;
    rmSync(fakeHome, { recursive: true, force: true });
    rmSync(project, { recursive: true, force: true });
  });

  it("escreve ~/.amp/<agent>/config.json (0600) com os campos do token", async () => {
    await run([encode(VALID), "--project", project, "--no-mcp"]);
    const path = join(fakeHome, ".amp", "backend-julio", "config.json");
    const config = JSON.parse(readFileSync(path, "utf-8"));
    expect(config).toMatchObject({
      hub_url: VALID.hub_url,
      agent_id: VALID.agent_id,
      agent_key: VALID.key,
      project_dir: project,
    });
    expect(statSync(path).mode & 0o777).toBe(0o600);
  });

  it("instala os dois hooks no settings.json do projeto (.claude criado se faltar)", async () => {
    await run([encode(VALID), "--project", project, "--no-mcp"]);
    const settings = JSON.parse(readFileSync(join(project, ".claude", "settings.json"), "utf-8"));
    const cmds = [
      ...settings.hooks.SessionStart[0].hooks.map((h: { command: string }) => h.command),
      ...settings.hooks.UserPromptSubmit[0].hooks.map((h: { command: string }) => h.command),
    ];
    expect(cmds.some((c: string) => c.endsWith("amp-session-start.sh"))).toBe(true);
    expect(cmds.some((c: string) => c.endsWith("amp-inbox.sh"))).toBe(true);
  });
});
