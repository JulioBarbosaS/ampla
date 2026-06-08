/**
 * The `amp` bin (global wrapper): dispatches subcommands to the local tsx.
 * Runs the bin as a real subprocess — proves the wiring that `pnpm link --global`
 * exposes as the `amp` command.
 */

import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

const BIN = resolve(import.meta.dirname, "../../bin/amp.mjs");
const token = (o: unknown) => Buffer.from(JSON.stringify(o)).toString("base64url");

function amp(args: string[], env: NodeJS.ProcessEnv = {}) {
  return spawnSync("node", [BIN, ...args], { env: { ...process.env, ...env }, encoding: "utf-8" });
}

describe("bin amp", () => {
  it("with no arguments prints usage and exits 0", () => {
    const r = amp([]);
    expect(r.status).toBe(0);
    expect(r.stderr).toMatch(/amp connect/);
  });

  it("invalid subcommand exits 1", () => {
    expect(amp(["xpto"]).status).toBe(1);
  });

  describe("connect dispatch", () => {
    let home: string;
    beforeEach(() => {
      home = mkdtempSync(join(tmpdir(), "amp-bin-home-"));
    });
    afterEach(() => rmSync(home, { recursive: true, force: true }));

    it("amp connect <token> writes the config (dispatches to the CLI)", () => {
      const tok = token({
        hub_url: "ws://localhost:8000/ws",
        agent_id: "backend-julio",
        key: `amp_${"cd".repeat(32)}`,
      });
      const r = amp(["connect", tok, "--project", "/tmp", "--no-mcp", "--no-hooks"], {
        HOME: home,
      });
      expect(r.status).toBe(0);
      expect(existsSync(join(home, ".amp", "backend-julio", "config.json"))).toBe(true);
    });
  });
});
