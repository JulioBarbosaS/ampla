/**
 * Testa o hook de onboarding amp-session-start.sh end-to-end: sobe um
 * servidor HTTP fake em unix socket respondendo /status, invoca o script
 * real e confere o JSON de contexto que ele emite para o Claude Code.
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

describe("hook amp-session-start", () => {
  it("injeta identidade, colegas online (sem o próprio) e não-lidas", async () => {
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
    expect(ctx).not.toContain("backend-julio na rede Ampla — outros"); // não se lista como colega
    expect(ctx).toContain("não lidas esperando você: 2");
    expect(ctx).toContain("amp_send");
  });

  it("sem colegas online diz 'ninguém'", async () => {
    await startDaemonFake({ agent_id: "solo-agent", online: ["solo-agent"], unread: 0 });
    const ctx = JSON.parse(await runHook()).hookSpecificOutput.additionalContext as string;
    expect(ctx).toContain("Colegas online agora: ninguém");
  });

  it("falha em silêncio (exit 0, sem saída) se o daemon não está rodando", async () => {
    // sem startDaemonFake → socket não existe
    const { stdout } = await run("bash", [HOOK], { env: { ...process.env, AMP_HOME: dir } });
    expect(stdout).toBe("");
  });
});
