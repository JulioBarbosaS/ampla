/**
 * Tests the onboarding hook amp-session-start.sh end-to-end: brings up a
 * fake HTTP server on a unix socket answering /status, invokes the real
 * script and checks the context JSON it emits for Claude Code.
 */

import { execFile } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { createServer, type Server } from "node:http";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { promisify } from "node:util";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

const run = promisify(execFile);
const HOOK = resolve(import.meta.dirname, "../../hooks/amp-session-start.sh");

let dir: string;
let sock: string;
let server: Server | null = null;

function startDaemonFake(status: unknown): Promise<void> {
  server = createServer((req, res) => {
    if (req.url === "/status") {
      res.setHeader("content-type", "application/json");
      res.end(JSON.stringify(status));
    } else {
      res.statusCode = 404;
      res.end("{}");
    }
  });
  return new Promise((r) => server!.listen(sock, () => r()));
}

async function runHook(): Promise<string> {
  const { stdout } = await run("bash", [HOOK], { env: { ...process.env, AMP_HOME: dir } });
  return stdout;
}

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "amp-hook-"));
  sock = join(dir, "daemon.sock");
});

afterEach(async () => {
  if (server) await new Promise<void>((r) => server!.close(() => r()));
  server = null;
  rmSync(dir, { recursive: true, force: true });
});

describe("amp-session-start hook", () => {
  it("injects identity, online peers (excluding self) and unread count", async () => {
    await startDaemonFake({
      agent_id: "backend-julio",
      connected: true,
      online: ["backend-julio", "mobile-eduardo", "infra-maria"],
      settings: { mode: "auto" },
      unread: 2,
    });
    const out = JSON.parse(await runHook());
    expect(out.hookSpecificOutput.hookEventName).toBe("SessionStart");
    const ctx = out.hookSpecificOutput.additionalContext as string;
    expect(ctx).toContain('agente "backend-julio"');
    expect(ctx).toContain("mobile-eduardo, infra-maria");
    expect(ctx).not.toContain("backend-julio na rede Ampla — outros"); // does not list itself as a peer
    expect(ctx).toContain("não lidas esperando você: 2");
    expect(ctx).toContain("amp_send");
  });

  it("with no online peers says 'ninguém'", async () => {
    await startDaemonFake({ agent_id: "solo-agent", online: ["solo-agent"], unread: 0 });
    const ctx = JSON.parse(await runHook()).hookSpecificOutput.additionalContext as string;
    expect(ctx).toContain("Colegas online agora: ninguém");
  });

  it("fails silently (exit 0, no output) if the daemon is not running", async () => {
    // no startDaemonFake → the socket does not exist
    const { stdout } = await run("bash", [HOOK], { env: { ...process.env, AMP_HOME: dir } });
    expect(stdout).toBe("");
  });
});
