/**
 * Daemon local configuration (~/.amp/config.json).
 *
 * Security (docs/ARCHITECTURE.md · Threat 4): ~/.amp with 0700,
 * files with 0600 — the agent's key lives here.
 */

import { chmodSync, existsSync, mkdirSync, readFileSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { z } from "zod";

export const daemonConfigSchema = z.object({
  hub_url: z.string().url(), // e.g. ws://localhost:4455/ws
  agent_id: z.string().regex(/^[a-z][a-z0-9-]{1,48}[a-z0-9]$/),
  agent_key: z.string().startsWith("amp_"),
  /** Repository directory used by auto-respond (cwd of claude -p). */
  project_dir: z.string().optional(),
  /** Claude Code binary (default: "claude" on PATH). */
  claude_bin: z.string().default("claude"),
  /** Where the auto-respond's claude -p runs:
   * - "host": directly (filesystem limited by in-process deny-rules only)
   * - "docker": in an ephemeral container that only mounts the project dir —
   *   the host filesystem is invisible (kernel-enforced). Needs Docker + the
   *   sandbox_image built (bridge/sandbox/Dockerfile). */
  sandbox: z.enum(["host", "docker"]).default("host"),
  sandbox_image: z.string().default("ampla/claude-runner:latest"),
  /** Capture token/cost usage by running `claude -p --output-format json` and
   * parsing it (Epic 03 · 3.4). OFF by default: the validated text-mode flow is
   * unchanged. Turn on (after smoke-testing your claude version) to populate the
   * transcript's usage fields AND enforce the per-agent daily token/cost budget —
   * the budget can only act on captured usage. */
  capture_usage: z.boolean().default(false),
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

/** Persisted daily auto-respond usage counter (Epic 03 · 3.4) — survives a
 * daemon restart so a bounce can't reset a budget mid-day. */
export function usagePath(): string {
  return join(ampDir(), "usage.json");
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
    // Loose permissions expose the key to other users on the machine
    chmodSync(path, 0o600);
  }
  return daemonConfigSchema.parse(JSON.parse(readFileSync(path, "utf-8")));
}
