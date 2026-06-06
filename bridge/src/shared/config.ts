/**
 * Configuração local do daemon (~/.amp/config.json).
 *
 * Segurança (docs/ARCHITECTURE.md · Ameaça 4): ~/.amp com 0700,
 * arquivos com 0600 — a chave do agente mora aqui.
 */

import { chmodSync, existsSync, mkdirSync, readFileSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { z } from "zod";

export const daemonConfigSchema = z.object({
  hub_url: z.string().url(), // ex: ws://localhost:8000/ws
  agent_id: z.string().regex(/^[a-z][a-z0-9-]{1,48}[a-z0-9]$/),
  agent_key: z.string().startsWith("amp_"),
  /** Diretório do repositório usado pelo auto-respond (cwd do claude -p). */
  project_dir: z.string().optional(),
  /** Binário do Claude Code (default: "claude" no PATH). */
  claude_bin: z.string().default("claude"),
});
export type DaemonConfig = z.infer<typeof daemonConfigSchema>;

export function ampDir(): string {
  return process.env.AMP_HOME ?? join(homedir(), ".amp");
}

export function ensureAmpDir(): string {
  const dir = ampDir();
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true, mode: 0o700 });
  } else {
    chmodSync(dir, 0o700);
  }
  return dir;
}

export function configPath(): string {
  return join(ampDir(), "config.json");
}

export function socketPath(): string {
  return join(ampDir(), "daemon.sock");
}

export function storePath(): string {
  return join(ampDir(), "messages.jsonl");
}

export function loadConfig(): DaemonConfig {
  const path = configPath();
  if (!existsSync(path)) {
    throw new Error(
      `Config não encontrada em ${path}. Crie com: {"hub_url", "agent_id", "agent_key"}.`,
    );
  }
  const mode = statSync(path).mode & 0o777;
  if ((mode & 0o077) !== 0) {
    // Permissão frouxa expõe a chave a outros usuários da máquina
    chmodSync(path, 0o600);
  }
  return daemonConfigSchema.parse(JSON.parse(readFileSync(path, "utf-8")));
}
