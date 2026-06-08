/**
 * Exercises the REAL defaultClaudeRunner (detached spawn, stdout parsing,
 * timeout with process-group kill, exit code) — code that until now only
 * ran mocked. Uses a FAKE "claude" (shell script) so as not to burn the
 * account nor depend on login: what matters is the real process path.
 */

import { chmodSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { defaultClaudeRunner } from "../../src/daemon/auto-responder.js";

let dir: string;

/** Creates an executable fake "claude" with the given bash body. */
function fakeClaude(body: string): string {
  const path = join(dir, "fake-claude.sh");
  writeFileSync(path, `#!/usr/bin/env bash\n${body}\n`, { mode: 0o755 });
  chmodSync(path, 0o755);
  return path;
}

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "amp-runner-"));
});
afterEach(() => rmSync(dir, { recursive: true, force: true }));

describe("defaultClaudeRunner (real process)", () => {
  it("happy path: captures and returns the binary's stdout", async () => {
    const bin = fakeClaude('echo "Sim: POST /api/v1/auth/password-reset"');
    const out = await defaultClaudeRunner("pergunta", { bin, timeoutMs: 5000 });
    expect(out).toBe("Sim: POST /api/v1/auth/password-reset");
  });

  it("receives the prompt as the -p argument", async () => {
    // the fake echoes the 2nd argument (the value of -p) — proves the prompt arrives
    const bin = fakeClaude('echo "$2"');
    const out = await defaultClaudeRunner("minha pergunta secreta", { bin, timeoutMs: 5000 });
    expect(out).toBe("minha pergunta secreta");
  });

  it("timeout: kills and rejects with 'timeout' within the deadline", async () => {
    const bin = fakeClaude("sleep 5; echo tarde-demais");
    const start = Date.now();
    await expect(defaultClaudeRunner("p", { bin, timeoutMs: 300 })).rejects.toThrow("timeout");
    expect(Date.now() - start).toBeLessThan(2000); // did not wait the full 5s
  });

  it("exit code != 0 becomes an error", async () => {
    const bin = fakeClaude("echo erro >&2; exit 3");
    await expect(defaultClaudeRunner("p", { bin, timeoutMs: 5000 })).rejects.toThrow("código 3");
  });

  it("respects the cwd (reads a file from the project directory)", async () => {
    writeFileSync(join(dir, "marcador.txt"), "conteudo-do-repo");
    const bin = fakeClaude("cat marcador.txt"); // relative to the cwd
    const out = await defaultClaudeRunner("p", { bin, cwd: dir, timeoutMs: 5000 });
    expect(out).toBe("conteudo-do-repo");
  });
});
