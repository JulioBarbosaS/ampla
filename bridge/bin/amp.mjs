#!/usr/bin/env node
/**
 * `amp` — thin bridge wrapper. Dispatches subcommands to the entries
 * via the local tsx (runs from src/, no build). Install globally with:
 *   cd bridge && pnpm link --global      # then: amp connect <token>
 */

import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const PKG = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const ENTRIES = {
  connect: "src/cli/connect.ts",
  daemon: "src/daemon/index.ts",
  mcp: "src/mcp/index.ts",
};

// Same shape the connection token enforces (src/cli/connect.ts).
const SLUG_RE = /^[a-z][a-z0-9-]{1,48}[a-z0-9]$/;

const tsx = resolve(PKG, "node_modules/.bin/tsx");
const bin = existsSync(tsx) ? tsx : "tsx"; // fallback to tsx on PATH

/** Runs an entry under the local tsx, inheriting stdio, then exits with its code. */
function runEntry(entry, args, extraEnv) {
  const result = spawnSync(bin, [resolve(PKG, entry), ...args], {
    stdio: "inherit",
    env: extraEnv ? { ...process.env, ...extraEnv } : process.env,
  });
  process.exit(result.status ?? 1);
}

function usage(code) {
  console.error("Uso: amp <connect|daemon|mcp> [args]");
  console.error("  amp connect <token>   conecta um agente (config + MCP + hooks)");
  console.error("  amp <agente> on       roda o daemon do agente (ex.: amp backend-julio on)");
  console.error("  amp daemon            roda o daemon (use AMP_HOME=~/.amp/<agente>)");
  console.error("  amp mcp               roda o servidor MCP (normalmente via claude mcp)");
  process.exit(code);
}

const [first, ...rest] = process.argv.slice(2);

// `amp <agente> on` — start the daemon for an agent already connected with
// `amp connect`. Sugar for `AMP_HOME=~/.amp/<agente> amp daemon`. Only when the
// first arg is NOT a known subcommand, so `amp daemon`/`amp mcp` keep working.
if (first && !ENTRIES[first] && rest[0] === "on") {
  if (!SLUG_RE.test(first)) {
    console.error(`Slug de agente inválido: ${first}`);
    process.exit(1);
  }
  const ampHome = join(homedir(), ".amp", first);
  if (!existsSync(join(ampHome, "config.json"))) {
    console.error(`Agente "${first}" não conectado (${join(ampHome, "config.json")} não existe).`);
    console.error("Conecte primeiro: amp connect <token>");
    process.exit(1);
  }
  runEntry(ENTRIES.daemon, [], { AMP_HOME: ampHome });
}

const entry = first ? ENTRIES[first] : undefined;
if (!entry) usage(first ? 1 : 0);
runEntry(entry, rest);
