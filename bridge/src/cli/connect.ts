/**
 * `amp connect <token>` — connect an agent in ONE command.
 *
 * Collapses the 6 manual steps (config.json, chmod, MCP, hooks) into one. The
 * token is what the panel shows after generating the key: base64url of
 * {hub_url, agent_id, key} — packed on the client, the hub does not change.
 *
 * Security: config written 0600 under ~/.amp/<agent>/ (0700); the key is never
 * logged; `claude mcp add` runs with args in an array (no shell). Hooks are
 * merged without overwriting existing ones. MCP/hooks can be skipped via flag.
 */

import { spawnSync } from "node:child_process";
import { chmodSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { createInterface } from "node:readline/promises";
import { pathToFileURL } from "node:url";
import { z } from "zod";
import { daemonConfigSchema } from "../shared/config.js";

/** Bridge package root — valid both when running from src/ (tsx) and from dist/. */
const BRIDGE_DIR = resolve(import.meta.dirname, "../..");

export const connectTokenSchema = z.object({
  hub_url: z.string().url(),
  agent_id: z.string().regex(/^[a-z][a-z0-9-]{1,48}[a-z0-9]$/),
  key: z.string().startsWith("amp_"),
});
export type ConnectToken = z.infer<typeof connectTokenSchema>;

/** Decodes and VALIDATES the connection token (base64url of a JSON). */
export function decodeToken(token: string): ConnectToken {
  let json: string;
  try {
    json = Buffer.from(token.trim(), "base64url").toString("utf-8");
  } catch {
    throw new Error("Token de conexão inválido (não é base64url).");
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(json);
  } catch {
    throw new Error("Token de conexão inválido (não decodifica para JSON).");
  }
  return connectTokenSchema.parse(parsed);
}

interface HookEntry {
  event: "SessionStart" | "UserPromptSubmit";
  command: string;
}

type Settings = { hooks?: Record<string, Array<{ hooks?: Array<{ command?: string }> }>> };

/**
 * Merges Ampla's hooks into an existing settings.json WITHOUT overwriting
 * whatever is already there. Idempotent: running again does not duplicate.
 */
export function mergeHookSettings(existing: Settings, entries: HookEntry[]): Settings {
  const next: Settings = { ...existing, hooks: { ...(existing.hooks ?? {}) } };
  const hooks = next.hooks as NonNullable<Settings["hooks"]>;
  for (const { event, command } of entries) {
    const groups = (hooks[event] ?? []).map((g) => ({ ...g }));
    const already = groups.some((g) => g.hooks?.some((h) => h.command === command));
    if (!already) groups.push({ hooks: [{ type: "command", command }] as never });
    hooks[event] = groups;
  }
  return next;
}

function writeAgentConfig(
  decoded: ConnectToken,
  projectDir: string | undefined,
  sandbox: boolean,
): string {
  const home = join(homedir(), ".amp", decoded.agent_id);
  mkdirSync(home, { recursive: true, mode: 0o700 });
  chmodSync(home, 0o700);
  const config = daemonConfigSchema.parse({
    hub_url: decoded.hub_url,
    agent_id: decoded.agent_id,
    agent_key: decoded.key,
    ...(projectDir ? { project_dir: resolve(projectDir) } : {}),
    claude_bin: "claude",
    ...(sandbox ? { sandbox: "docker" } : {}),
  });
  const path = join(home, "config.json");
  writeFileSync(path, `${JSON.stringify(config, null, 2)}\n`, { mode: 0o600 });
  chmodSync(path, 0o600);
  return home;
}

function registerMcp(home: string): boolean {
  const result = spawnSync(
    "claude",
    ["mcp", "add", "ampla", "-e", `AMP_HOME=${home}`, "--", "pnpm", "--dir", BRIDGE_DIR, "mcp"],
    { stdio: "ignore" },
  );
  return result.status === 0;
}

function installHooks(projectDir: string): string {
  const settingsPath = join(projectDir, ".claude", "settings.json");
  mkdirSync(dirname(settingsPath), { recursive: true });
  const existing: Settings = existsSync(settingsPath)
    ? JSON.parse(readFileSync(settingsPath, "utf-8"))
    : {};
  const merged = mergeHookSettings(existing, [
    { event: "SessionStart", command: join(BRIDGE_DIR, "hooks", "amp-session-start.sh") },
    { event: "UserPromptSubmit", command: join(BRIDGE_DIR, "hooks", "amp-inbox.sh") },
  ]);
  writeFileSync(settingsPath, `${JSON.stringify(merged, null, 2)}\n`);
  return settingsPath;
}

interface Flags {
  project?: string;
  noMcp: boolean;
  noHooks: boolean;
  start: boolean;
  sandbox: boolean;
}

function parseArgs(argv: string[]): { token: string; flags: Flags } {
  let token = "";
  const flags: Flags = { noMcp: false, noHooks: false, start: false, sandbox: false };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "--no-mcp") flags.noMcp = true;
    else if (arg === "--no-hooks") flags.noHooks = true;
    else if (arg === "--start") flags.start = true;
    else if (arg === "--sandbox") flags.sandbox = true;
    else if (arg === "--project") {
      const value = argv[++i];
      if (value) flags.project = value;
    } else if (!arg?.startsWith("--")) token = arg ?? "";
  }
  if (!token)
    throw new Error(
      "Uso: amp connect <token> [--project DIR] [--no-mcp] [--no-hooks] [--start] [--sandbox]",
    );
  return { token, flags };
}

async function promptProject(): Promise<string | undefined> {
  if (!process.stdin.isTTY) return undefined; // non-interactive: skip without blocking
  const rl = createInterface({ input: process.stdin, output: process.stdout });
  try {
    const answer = (
      await rl.question(`Diretório do projeto deste agente (enter = atual ${process.cwd()}): `)
    ).trim();
    return answer || undefined;
  } finally {
    rl.close();
  }
}

export async function run(argv: string[]): Promise<void> {
  const { token, flags } = parseArgs(argv);
  const decoded = decodeToken(token);

  // Empty (or non-interactive) defaults to the current directory — that is the
  // cwd the auto-responder's claude -p runs in, so it must be explicit, not a
  // surprise inherited from the daemon's launch dir.
  const project = flags.project ?? (await promptProject()) ?? process.cwd();
  const home = writeAgentConfig(decoded, project, flags.sandbox);
  console.error(`✓ config  → ${join(home, "config.json")} (0600)`);

  if (!flags.noMcp) {
    if (registerMcp(home)) console.error("✓ MCP 'ampla' registrado no Claude Code");
    else
      console.error("⚠ não consegui registrar o MCP (claude no PATH?). Pulei — registre depois.");
  }
  if (!flags.noHooks) {
    const where = installHooks(project);
    console.error(`✓ hooks de onboarding instalados → ${where}`);
  }

  const daemonCmd = `AMP_HOME=${home} pnpm --dir ${BRIDGE_DIR} daemon`;
  if (flags.start) {
    console.error("→ iniciando o daemon…");
    spawnSync("pnpm", ["--dir", BRIDGE_DIR, "daemon"], {
      env: { ...process.env, AMP_HOME: home },
      stdio: "inherit",
    });
  } else {
    console.error(`→ rode:  ${daemonCmd}`);
  }
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  run(process.argv.slice(2)).catch((error) => {
    console.error(`[amp connect] ${error instanceof Error ? error.message : error}`);
    process.exit(1);
  });
}
