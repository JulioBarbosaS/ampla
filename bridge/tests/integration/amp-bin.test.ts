/**
 * The `amp` bin (global wrapper): dispatches subcommands to the local tsx.
 * Runs the bin as a real subprocess — proves the wiring that `pnpm link --global`
 * exposes as the `amp` command.
 */

import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
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

  describe("amp <agente> on (start the daemon)", () => {
    let home: string;
    beforeEach(() => {
      home = mkdtempSync(join(tmpdir(), "amp-bin-on-"));
    });
    afterEach(() => rmSync(home, { recursive: true, force: true }));

    it("errors (exit 1) when the agent was never connected", () => {
      const r = amp(["backend-julio", "on"], { HOME: home });
      expect(r.status).toBe(1);
      expect(r.stderr).toMatch(/não conectado/);
    });

    it("rejects an invalid slug", () => {
      const r = amp(["Not A Slug", "on"], { HOME: home });
      expect(r.status).toBe(1);
      expect(r.stderr).toMatch(/inválido/);
    });

    it("dispatches into the daemon with AMP_HOME=~/.amp/<agente> when connected", () => {
      // A present-but-invalid config passes the `on` guard (file exists) and is
      // then rejected by the daemon — proving dispatch resolved AMP_HOME and ran
      // the daemon against THAT config, without leaving a long-running process.
      mkdirSync(join(home, ".amp", "backend-julio"), { recursive: true });
      writeFileSync(join(home, ".amp", "backend-julio", "config.json"), "{}");
      const r = amp(["backend-julio", "on"], { HOME: home });
      expect(r.status).not.toBe(0);
      expect(r.stderr).not.toMatch(/não conectado/); // got past the guard, into the daemon
      expect(r.stderr).toMatch(/erro fatal/); // the daemon read the (invalid) config there
    });
  });
});
