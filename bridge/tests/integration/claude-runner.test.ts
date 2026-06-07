/**
 * Exercita o defaultClaudeRunner REAL (spawn detached, parsing de stdout,
 * timeout com kill de process-group, exit code) — código que até aqui só
 * rodava mockado. Usa um "claude" FALSO (script shell) para não gastar a
 * conta nem depender de login: o que importa é o caminho de processo real.
 */

import { chmodSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { defaultClaudeRunner } from "../../src/daemon/auto-responder.js";

let dir: string;

/** Cria um "claude" falso executável com o corpo bash dado. */
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

describe("defaultClaudeRunner (processo real)", () => {
  it("caminho feliz: captura e devolve o stdout do binário", async () => {
    const bin = fakeClaude('echo "Sim: POST /api/v1/auth/password-reset"');
    const out = await defaultClaudeRunner("pergunta", { bin, timeoutMs: 5000 });
    expect(out).toBe("Sim: POST /api/v1/auth/password-reset");
  });

  it("recebe o prompt como argumento -p", async () => {
    // o fake ecoa o 2º argumento (valor de -p) — prova que o prompt chega
    const bin = fakeClaude('echo "$2"');
    const out = await defaultClaudeRunner("minha pergunta secreta", { bin, timeoutMs: 5000 });
    expect(out).toBe("minha pergunta secreta");
  });

  it("timeout: mata e rejeita com 'timeout' dentro do prazo", async () => {
    const bin = fakeClaude("sleep 5; echo tarde-demais");
    const start = Date.now();
    await expect(defaultClaudeRunner("p", { bin, timeoutMs: 300 })).rejects.toThrow("timeout");
    expect(Date.now() - start).toBeLessThan(2000); // não esperou os 5s
  });

  it("exit code != 0 vira erro", async () => {
    const bin = fakeClaude("echo erro >&2; exit 3");
    await expect(defaultClaudeRunner("p", { bin, timeoutMs: 5000 })).rejects.toThrow("código 3");
  });

  it("respeita o cwd (lê arquivo do diretório do projeto)", async () => {
    writeFileSync(join(dir, "marcador.txt"), "conteudo-do-repo");
    const bin = fakeClaude("cat marcador.txt"); // relativo ao cwd
    const out = await defaultClaudeRunner("p", { bin, cwd: dir, timeoutMs: 5000 });
    expect(out).toBe("conteudo-do-repo");
  });
});
