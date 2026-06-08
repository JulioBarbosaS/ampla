/**
 * `amp connect <token>`: token decode/validation, non-destructive merge
 * of the hooks and the integration that writes the config (0600) + installs the hooks.
 * MCP is skipped (--no-mcp) so as not to depend on the real `claude`.
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
  it("decodes and validates a good token", () => {
    expect(decodeToken(encode(VALID))).toEqual(VALID);
  });

  it("rejects base64 that is not JSON", () => {
    expect(() => decodeToken(Buffer.from("xpto").toString("base64url"))).toThrow();
  });

  it("rejects invalid fields (key without amp_)", () => {
    expect(() => decodeToken(encode({ ...VALID, key: "sem-prefixo" }))).toThrow();
  });

  it("rejects an agent_id outside the slug pattern", () => {
    expect(() => decodeToken(encode({ ...VALID, agent_id: "Tem Maiúscula" }))).toThrow();
  });
});

describe("mergeHookSettings", () => {
  const entries = [
    { event: "SessionStart" as const, command: "/x/amp-session-start.sh" },
    { event: "UserPromptSubmit" as const, command: "/x/amp-inbox.sh" },
  ];

  it("adds both hooks", () => {
    const merged = mergeHookSettings({}, entries);
    expect(merged.hooks?.SessionStart).toHaveLength(1);
    expect(merged.hooks?.UserPromptSubmit?.[0]?.hooks?.[0]?.command).toBe("/x/amp-inbox.sh");
  });

  it("is idempotent (does not duplicate)", () => {
    const once = mergeHookSettings({}, entries);
    const twice = mergeHookSettings(once, entries);
    expect(twice.hooks?.SessionStart).toHaveLength(1);
  });

  it("preserves already-existing hooks and keys", () => {
    const existing = {
      model: "opus",
      hooks: { SessionStart: [{ hooks: [{ command: "/outro.sh" }] }] },
    };
    const merged = mergeHookSettings(existing, entries) as typeof existing & { model: string };
    expect(merged.model).toBe("opus");
    expect(merged.hooks?.SessionStart).toHaveLength(2); // the user's + ours
  });
});

describe("run (integration: writes config + hooks)", () => {
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

  it("writes ~/.amp/<agent>/config.json (0600) with the token fields", async () => {
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

  it("installs both hooks in the project's settings.json (.claude created if missing)", async () => {
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
